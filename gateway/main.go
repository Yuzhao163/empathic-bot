package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/redis/go-redis/v9"
)

// ============================================================================
// Types
// ============================================================================

type ChatRequest struct {
	SessionID string    `json:"session_id"`
	Message  string    `json:"message"`
	Emotion  string    `json:"emotion,omitempty"`
	Context  []Message `json:"context,omitempty"`
}

type ChatResponse struct {
	SessionID    string  `json:"session_id"`
	Message      string  `json:"message"`
	Emotion      string  `json:"emotion"`
	EmotionProb  float64 `json:"emotion_prob"`
	Advice       string  `json:"advice,omitempty"`
	Timestamp    int64   `json:"timestamp"`
}

type EmotionResult struct {
	Emotion string  `json:"emotion"`
	Prob    float64 `json:"prob"`
	Emoji   string  `json:"emoji,omitempty"`
	Advice  string  `json:"advice,omitempty"`
}

type Message struct {
	Role      string `json:"role"`
	Content   string `json:"content"`
	Emotion   string `json:"emotion,omitempty"`
	Timestamp int64  `json:"timestamp,omitempty"`
}

type LLMResponse struct {
	Text        string  `json:"text"`
	Emotion     string  `json:"emotion"`
	EmotionProb float64 `json:"emotion_prob"`
	Advice      string  `json:"advice,omitempty"`
}

// ============================================================================
// Config
// ============================================================================

var (
	allowedOrigins []string
	redisAddr      string
)

func init() {
	originsEnv := getEnv("ALLOWED_ORIGINS", "")
	if originsEnv != "" {
		for _, o := range strings.Split(originsEnv, ",") {
			o = strings.TrimSpace(o)
			if o != "" {
				allowedOrigins = append(allowedOrigins, o)
			}
		}
	}
	// 默认允许 localhost 开发
	if len(allowedOrigins) == 0 {
		allowedOrigins = []string{"http://localhost:3000"}
	}
}

func isOriginAllowed(origin string) bool {
	for _, allowed := range allowedOrigins {
		if allowed == origin {
			return true
		}
	}
	return false
}

// ============================================================================
// Redis — SCAN 替代 KEYS
// ============================================================================

type redisStore struct {
	client *redis.Client
}

func (s *redisStore) lpushMessage(ctx context.Context, sessionID, data string) error {
	key := fmt.Sprintf("session:%s:messages", sessionID)
	pipe := s.client.Pipeline()
	pipe.LPush(ctx, key, data)
	pipe.Expire(ctx, key, 7*24*time.Hour)
	_, err := pipe.Exec(ctx)
	return err
}

func (s *redisStore) getMessages(ctx context.Context, sessionID string, offset, limit int64) ([]Message, error) {
	key := fmt.Sprintf("session:%s:messages", sessionID)
	data, err := s.client.LRange(ctx, key, offset, limit).Result()
	if err != nil {
		return nil, err
	}
	var history []Message
	for _, item := range data {
		var msg Message
		if json.Unmarshal([]byte(item), &msg) == nil {
			history = append(history, msg)
		}
	}
	// 反转：最老的在前
	for i, j := 0, len(history)-1; i < j; i, j = i+1, j-1 {
		history[i], history[j] = history[j], history[i]
	}
	return history, nil
}

func (s *redisStore) listSessions(ctx context.Context) ([]sessionInfo, error) {
	var sessions []sessionInfo
	var cursor uint64
	for {
		keys, nextCursor, err := s.client.Scan(ctx, cursor, "session:*:messages", 100).Result()
		if err != nil {
			return nil, err
		}
		for _, key := range keys {
			msgs, _ := s.client.LRange(ctx, key, 0, 0).Result()
			title := "新对话"
			if len(msgs) > 0 {
				var msg Message
				if json.Unmarshal([]byte(msgs[0]), &msg) == nil {
					content := msg.Content
					if len(content) > 25 {
						title = content[:25] + "..."
					} else {
						title = content
					}
				}
			}
			sessionID := key[len("session:") : len(key)-len(":messages")]
			sessions = append(sessions, sessionInfo{sessionID: sessionID, title: title})
		}
		cursor = nextCursor
		if cursor == 0 {
			break
		}
	}
	return sessions, nil
}

type sessionInfo struct {
	sessionID string
	title     string
}

func (s *redisStore) deleteSession(ctx context.Context, sessionID string) error {
	key := fmt.Sprintf("session:%s:messages", sessionID)
	return s.client.Del(ctx, key).Err()
}

// ============================================================================
// Rate Limiter — Per-IP
// ============================================================================

type ipLimiter struct {
	mu      sync.Mutex
	limiters map[string]*tokenBucket
}

type tokenBucket struct {
	tokens     float64
	lastRefill time.Time
	rate       float64
	burst      float64
}

func newIPLimiter() *ipLimiter {
	return &ipLimiter{limiters: make(map[string]*tokenBucket)}
}

func (l *ipLimiter) Allow(ip string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	bucket, ok := l.limiters[ip]
	if !ok {
		bucket = &tokenBucket{tokens: 20, lastRefill: time.Now(), rate: 10, burst: 20}
		l.limiters[ip] = bucket
	}
	now := time.Now()
	elapsed := now.Sub(bucket.lastRefill).Seconds()
	bucket.lastRefill = now
	bucket.tokens += elapsed * bucket.rate
	if bucket.tokens > bucket.burst {
		bucket.tokens = bucket.burst
	}
	if bucket.tokens >= 1 {
		bucket.tokens--
		return true
	}
	return false
}

var ipLimiter = newIPLimiter()

// ============================================================================
// Scheduler — Worker Pool
// ============================================================================

type Scheduler struct {
	pendingCh    chan *ChatRequest
	pendingOnce  map[string]chan *ChatResponse
	pendingMu    sync.Mutex
	ctx          context.Context
	cancel       context.CancelFunc
	wg           sync.WaitGroup
}

func NewScheduler() *Scheduler {
	ctx, cancel := context.WithCancel(context.Background())
	s := &Scheduler{
		pendingCh:   make(chan *ChatRequest, 200),
		pendingOnce: make(map[string]chan *ChatResponse),
		ctx:         ctx,
		cancel:      cancel,
	}
	// 固定 10 个 worker，避免 goroutine 爆炸
	for i := 0; i < 10; i++ {
		s.wg.Add(1)
		go s.worker(i)
	}
	return s
}

func (s *Scheduler) worker(id int) {
	defer s.wg.Done()
	for {
		select {
		case <-s.ctx.Done():
			return
		case req, ok := <-s.pendingCh:
			if !ok {
				return
			}
			s.callLLMService(req)
		}
	}
}

func (s *Scheduler) Shutdown() {
	s.cancel()
	close(s.pendingCh)
	s.wg.Wait()
}

func (s *Scheduler) callLLMService(req *ChatRequest) {
	history := store.getMessages(context.Background(), req.SessionID)

	payload := map[string]any{
		"message": req.Message,
		"context": history,
		"emotion": req.Emotion,
	}

	var resp *LLMResponse
	var err error
	for _, provider := range availableLLMProviders {
		resp, err = callLLMServiceWithRetry(provider, payload)
		if err == nil {
			break
		}
		slog.Warn("llm provider failed", "provider", provider, "err", err)
	}

	if err != nil || resp == nil {
		emotion := req.Emotion
		if emotion == "" {
			emotion = "neutral"
		}
		resp = &LLMResponse{
			Text:        "我在这里，愿意听你说。有什么想聊的？",
			Emotion:     emotion,
			EmotionProb: 0.70,
			Advice:      "💙 感谢分享，继续说吧，我在这里倾听。",
		}
	}

	store.lpushMessage(context.Background(), req.SessionID, mustMarshal(Message{
		Role:      "assistant",
		Content:   resp.Text,
		Emotion:   resp.Emotion,
		Timestamp: time.Now().UnixMilli(),
	}))

	chatResp := &ChatResponse{
		SessionID:    req.SessionID,
		Message:      resp.Text,
		Emotion:      resp.Emotion,
		EmotionProb:  resp.EmotionProb,
		Advice:       resp.Advice,
		Timestamp:    time.Now().UnixMilli(),
	}

	s.pendingMu.Lock()
	if ch, ok := s.pendingOnce[req.SessionID]; ok {
		select {
		case ch <- chatResp:
		default:
		}
		delete(s.pendingOnce, req.SessionID)
	}
	s.pendingMu.Unlock()
}

func callLLMServiceWithRetry(provider string, payload map[string]any) (*LLMResponse, error) {
	body, _ := json.Marshal(payload)
	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(1<<attempt) * time.Second) // 1s, 2s, 4s
		}
		req, err := http.NewRequest("POST", provider+"/chat", strings.NewReader(string(body)))
		if err != nil {
			lastErr = err
			continue
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("User-Agent", "empathic-gateway/1.0")

		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		client := &http.Client{Timeout: 30 * time.Second}
		resp, err := client.Do(req.WithContext(ctx))
		cancel()
		if err != nil {
			lastErr = err
			continue
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			lastErr = fmt.Errorf("llm status %d", resp.StatusCode)
			continue
		}
		var result LLMResponse
		if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
			lastErr = err
			continue
		}
		return &result, nil
	}
	return nil, lastErr
}

// ============================================================================
// LLM Service Discovery
// ============================================================================

var availableLLMProviders = []string{
	"http://python_service:8001",
	"http://localhost:8001",
}

// ============================================================================
// Emotion Detection
// ============================================================================

type emotionKW struct {
	words  []string
	label  string
	prob   float64
	emoji  string
	advice string
}

var emotionLexicon = []emotionKW{
	{[]string{"开心","高兴","快乐","棒","很好","谢谢","喜欢","爱","美好","幸福","欢欣","happy","great","wonderful","love","excited","joy","awesome"}, "positive", 0.85, "😊", "💖 保持好心情！记录让你开心的事。"},
	{[]string{"难过","伤心","痛苦","抑郁","崩溃","sad","hurt","depressed","crying","misery","heartbroken"}, "negative", 0.80, "💙", "💙 难过时，深呼吸。和信任的人聊聊会有帮助。"},
	{[]string{"焦虑","担心","害怕","紧张","不安","压力","恐惧","anxious","worried","scared","nervous","stress","fear","panic"}, "anxious", 0.78, "🌸", "🌸 焦虑时，试着做5次深呼吸，专注当下。"},
	{[]string{"生气","愤怒","讨厌","烦","火","暴躁","angry","hate","furious","mad","annoyed","rage","irritated"}, "angry", 0.82, "🤍", "🤍 愤怒是正常的。描述你的感受，而不是压抑它。"},
	{[]string{"哭泣","流泪","泪","sad","hurt","crying","tears","heartache","grief"}, "sad", 0.80, "😢", "😢 允许自己感受这些情绪，你值得被爱。"},
}

func analyzeEmotion(text string) EmotionResult {
	if text == "" {
		return EmotionResult{"neutral", 0.70, "🌿", "🌿 感谢分享，继续说吧。"}
	}
	textLower := strings.ToLower(text)
	for _, e := range emotionLexicon {
		for _, kw := range e.words {
			if strings.Contains(textLower, kw) {
				return EmotionResult{e.label, e.prob, e.emoji, e.advice}
			}
		}
	}
	return EmotionResult{"neutral", 0.70, "🌿", "🌿 感谢分享，还有什么想聊的吗？"}
}

// ============================================================================
// Session ID — crypto/rand
// ============================================================================

func newSessionID() string {
	b := make([]byte, 16)
	FillRandom(b)
	return fmt.Sprintf("%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:16])
}

// ============================================================================
// HTTP Handlers
// ============================================================================

var store *redisStore
var scheduler *Scheduler

func main() {
	store = newRedisStore()
	scheduler = NewScheduler()
	defer scheduler.Shutdown()

	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(corsMiddleware())
	r.Use(ipRateLimitMiddleware())

	r.POST("/api/chat", handleChat)
	r.GET("/api/history/:session_id", handleHistory)
	r.DELETE("/api/history/:session_id", handleClearHistory)
	r.GET("/api/sessions", handleSessions)
	r.POST("/api/emotion/analyze", handleEmotionAnalyze)
	r.POST("/api/emotion/trend", handleEmotionTrend)

	r.GET("/ws/chat", handleWebSocket)
	r.GET("/health", handleHealth)

	addr := getEnv("PORT", "8080")
	slog.Info("gateway started", "addr", addr)
	if err := r.Run(":" + addr); err != nil {
		slog.Error("server error", "err", err)
	}
}

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------

var originCheck = regexp.MustCompile(`^https?://`)

func corsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		origin := c.Request.Header.Get("Origin")
		if origin != "" && originCheck.MatchString(origin) {
			if isOriginAllowed(origin) {
				c.Writer.Header().Set("Access-Control-Allow-Origin", origin)
				c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")
			}
		}
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type,Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	}
}

func ipRateLimitMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		ip := c.ClientIP()
		if !ipLimiter.Allow(ip) {
			c.JSON(429, gin.H{"error": "rate limit exceeded, please slow down"})
			c.Abort()
			return
		}
		c.Next()
	}
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

func handleChat(c *gin.Context) {
	var req ChatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": "invalid request: " + err.Error()})
		return
	}
	if req.Message == "" {
		c.JSON(400, gin.H{"error": "message is required"})
		return
	}
	// 消息长度限制
	if len(req.Message) > 2000 {
		c.JSON(400, gin.H{"error": "message too long, max 2000 characters"})
		return
	}

	if req.SessionID == "" {
		req.SessionID = newSessionID()
	}

	// 保存用户消息
	store.lpushMessage(c.Request.Context(), req.SessionID, mustMarshal(Message{
		Role:      "user",
		Content:   req.Message,
		Emotion:   req.Emotion,
		Timestamp: time.Now().UnixMilli(),
	}))

	resp := scheduler.ScheduleChat(&req)
	c.JSON(200, resp)
}

func (s *Scheduler) ScheduleChat(req *ChatRequest) *ChatResponse {
	ch := make(chan *ChatResponse, 1)
	s.pendingMu.Lock()
	s.pendingOnce[req.SessionID] = ch
	s.pendingMu.Unlock()

	select {
	case s.pendingCh <- req:
	default:
		return &ChatResponse{
			SessionID:   req.SessionID,
			Message:     "请求积压，请稍后再试。",
			Emotion:     "neutral",
			EmotionProb: 0.7,
			Timestamp:   time.Now().UnixMilli(),
		}
	}

	select {
	case resp := <-ch:
		return resp
	case <-time.After(30 * time.Second):
		return &ChatResponse{
			SessionID:   req.SessionID,
			Message:     "抱歉，响应超时，请稍后再试。",
			Emotion:     "neutral",
			EmotionProb: 0.7,
			Timestamp:   time.Now().UnixMilli(),
		}
	}
}

func handleHistory(c *gin.Context) {
	sessionID := c.Param("session_id")
	history, err := store.getMessages(c.Request.Context(), sessionID, 0, 99)
	if err != nil {
		c.JSON(500, gin.H{"error": "failed to load history"})
		return
	}
	c.JSON(200, gin.H{"session_id": sessionID, "messages": history})
}

func handleClearHistory(c *gin.Context) {
	sessionID := c.Param("session_id")
	if err := store.deleteSession(c.Request.Context(), sessionID); err != nil {
		c.JSON(500, gin.H{"error": "failed to delete session"})
		return
	}
	c.JSON(200, gin.H{"ok": true})
}

func handleSessions(c *gin.Context) {
	sessions, err := store.listSessions(c.Request.Context())
	if err != nil {
		c.JSON(500, gin.H{"error": "failed to list sessions"})
		return
	}
	result := make([]gin.H, 0, len(sessions))
	for _, s := range sessions {
		result = append(result, gin.H{"session_id": s.sessionID, "title": s.title})
	}
	c.JSON(200, gin.H{"sessions": result})
}

func handleEmotionAnalyze(c *gin.Context) {
	var req struct{ Text string `json:"text"` }
	if err := c.ShouldBindJSON(&req); err != nil || req.Text == "" {
		c.JSON(400, gin.H{"error": "text is required"})
		return
	}
	if len(req.Text) > 2000 {
		c.JSON(400, gin.H{"error": "text too long"})
		return
	}
	result := analyzeEmotion(req.Text)
	c.JSON(200, result)
}

func handleEmotionTrend(c *gin.Context) {
	var req struct {
		Messages []Message `json:"messages"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": "invalid request"})
		return
	}

	userEmotions := make([]EmotionResult, 0)
	for _, m := range req.Messages {
		if m.Role == "user" {
			userEmotions = append(userEmotions, analyzeEmotion(m.Content))
		}
	}

	emotionCount := make(map[string]int)
	for _, e := range userEmotions {
		emotionCount[e.Emotion]++
	}
	dominant := "neutral"
	maxCount := 0
	for emo, cnt := range emotionCount {
		if cnt > maxCount {
			maxCount = cnt
			dominant = emo
		}
	}

	c.JSON(200, gin.H{
		"emotions":  userEmotions,
		"dominant":  dominant,
		"count":     emotionCount,
	})
}

func handleHealth(c *gin.Context) {
	_, err := store.client.Ping(c.Request.Context()).Result()
	redisOK := err == nil

	// 检查下游 Python Service
	pythonOK := false
	for _, provider := range availableLLMProviders {
		ctx, cancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
		req, _ := http.NewRequestWithContext(ctx, "GET", provider+"/health", nil)
		client := &http.Client{Timeout: 3 * time.Second}
		resp, err := client.Do(req)
		cancel()
		if err == nil && resp.StatusCode == 200 {
			pythonOK = true
			resp.Body.Close()
			break
		}
	}

	healthy := redisOK && pythonOK
	c.JSON(200, gin.H{
		"status":   "ok",
		"service":  "gateway",
		"redis":    redisOK,
		"python":   pythonOK,
		"healthy":  healthy,
		"version":  "1.1.0",
	})
}

// ---------------------------------------------------------------------------
// WebSocket — Origin 校验 + 消息频率限制
// ---------------------------------------------------------------------------

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		origin := r.Header.Get("Origin")
		if origin == "" {
			return true // 同源 WS 不带 Origin
		}
		return isOriginAllowed(origin)
	},
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
}

type wsConnLimiter struct {
	mu    sync.Mutex
	count map[string]int
	last  map[string]time.Time
}

func newWSConnLimiter() *wsConnLimiter {
	return &wsConnLimiter{count: make(map[string]int), last: make(map[string]time.Time)}
}

var wsLimiter = newWSConnLimiter()

func (l *wsConnLimiter) Allow(ip string, msgRate int) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	l.count[ip]++
	l.last[ip] = now
	if l.count[ip] > msgRate*10 { // 超过10倍认为是滥用
		return false
	}
	// 每秒重置
	if now.Sub(l.last[ip]) > time.Second {
		l.count[ip] = 1
	}
	return true
}

func handleWebSocket(c *gin.Context) {
	ip := c.ClientIP()
	if !wsLimiter.Allow(ip, 10) {
		c.JSON(429, gin.H{"error": "too many connections"})
		return
	}

	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		slog.Warn("ws upgrade error", "err", err)
		return
	}
	defer conn.Close()

	sessionID := c.Query("session_id")
	if sessionID == "" {
		sessionID = newSessionID()
	}

	for {
		_, msgBytes, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				slog.Warn("ws read error", "err", err)
			}
			break
		}

		var req ChatRequest
		if json.Unmarshal(msgBytes, &req) != nil {
			continue
		}
		if len(req.Message) > 2000 {
			continue
		}
		req.SessionID = sessionID

		store.lpushMessage(c.Request.Context(), sessionID, mustMarshal(Message{
			Role:      "user",
			Content:   req.Message,
			Timestamp: time.Now().UnixMilli(),
		}))

		go func(r ChatRequest) {
			resp := scheduler.ScheduleChat(&r)
			resp.SessionID = r.SessionID
			respJSON, _ := json.Marshal(resp)
			if err := conn.WriteMessage(websocket.TextMessage, respJSON); err != nil {
				slog.Warn("ws write error", "err", err)
			}
		}(req)
	}
}

// ---------------------------------------------------------------------------
// Redis Init
// ---------------------------------------------------------------------------

func newRedisStore() *redisStore {
	addr := getEnv("REDIS_URL", "localhost:6379")
	if strings.HasPrefix(addr, "redis://") {
		addr = addr[9:]
	}
	rdb := redis.NewClient(&redis.Options{
		Addr:         addr,
		DialTimeout:  5 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
		PoolSize:    20,
	})
	return &redisStore{client: rdb}
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func mustMarshal(v any) string {
	b, _ := json.Marshal(v)
	return string(b)
}
