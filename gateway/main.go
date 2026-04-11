package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
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
	Text       string  `json:"text"`
	Emotion    string  `json:"emotion"`
	EmotionProb float64 `json:"emotion_prob"`
	Advice     string  `json:"advice,omitempty"`
}

// ============================================================================
// Scheduler — 参考 Ollama Scheduler 三 goroutine 并发模型
// ============================================================================

type Scheduler struct {
	pendingCh  chan *ChatRequest
	emotionCh  chan *ChatRequest
	doneCh     chan *ChatResponse
	pendingMu  sync.Mutex
	pendingOnce map[string]chan *ChatResponse
}

func NewScheduler() *Scheduler {
	s := &Scheduler{
		pendingCh:   make(chan *ChatRequest, 200),
		emotionCh:   make(chan *ChatRequest, 100),
		doneCh:      make(chan *ChatResponse, 200),
		pendingOnce: make(map[string]chan *ChatResponse),
	}
	go s.processRequests()   // 主调度：调用 LLM
	go s.processEmotions()   // 情绪分析
	go s.processResponses() // 响应聚合、存储
	return s
}

func (s *Scheduler) processRequests() {
	for req := range s.pendingCh {
		go s.callLLMService(req)
	}
}

func (s *Scheduler) processEmotions() {
	for req := range s.emotionCh {
		go func(r *ChatRequest) {
			result := analyzeEmotion(r.Message)
			log.Printf("[Emotion] session=%s emotion=%s prob=%.2f", r.SessionID, result.Emotion, result.Prob)
		}(req)
	}
}

func (s *Scheduler) processResponses() {
	for resp := range s.doneCh {
		// 写入 Redis
		data, _ := json.Marshal(Message{
			Role:      "assistant",
			Content:   resp.Message,
			Emotion:   resp.Emotion,
			Timestamp: resp.Timestamp,
		})
		key := fmt.Sprintf("session:%s:messages", resp.SessionID)
		rdb.LPush(ctx, key, string(data))
		rdb.Expire(ctx, key, 7*24*time.Hour)

		// 通知等待中的客户端
		s.pendingMu.Lock()
		if ch, ok := s.pendingOnce[resp.SessionID]; ok {
			select {
			case ch <- resp:
			default:
			}
			delete(s.pendingOnce, resp.SessionID)
		}
		s.pendingMu.Unlock()
	}
}

// ============================================================================
// LLM Service — 多模型降级
// ============================================================================

var availableLLMProviders = []string{
	"http://python_service:8001",
	"http://localhost:8001",
}

var currentLLMProvider = 0

func callLLMService(provider string, payload map[string]any) (*LLMResponse, error) {
	body, _ := json.Marshal(payload)
	req, _ := http.NewRequest("POST", provider+"/chat", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "empathic-gateway/1.0")

	// 带超时
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("llm status %d", resp.StatusCode)
	}

	var result LLMResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (s *Scheduler) callLLMService(req *ChatRequest) {
	history := s.loadHistory(req.SessionID)

	payload := map[string]any{
		"message":  req.Message,
		"context":  history,
		"emotion":  req.Emotion,
	}

	// 多模型降级：依次尝试可用服务
	var resp *LLMResponse
	var err error
	for i := 0; i < len(availableLLMProviders); i++ {
		idx := (currentLLMProvider + i) % len(availableLLMProviders)
		provider := availableLLMProviders[idx]
		resp, err = callLLMService(provider, payload)
		if err == nil {
			currentLLMProvider = idx
			break
		}
		log.Printf("[LLM] provider %s failed: %v", provider, err)
	}

	// 全部失败 → fallback
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

	// 并行做情绪分析（不阻塞）
	s.emotionCh <- req

	s.doneCh <- &ChatResponse{
		SessionID:    req.SessionID,
		Message:      resp.Text,
		Emotion:      resp.Emotion,
		EmotionProb:  resp.EmotionProb,
		Advice:       resp.Advice,
		Timestamp:    time.Now().UnixMilli(),
	}
}

func (s *Scheduler) loadHistory(sessionID string) []Message {
	key := fmt.Sprintf("session:%s:messages", sessionID)
	data, _ := rdb.LRange(ctx, key, 0, 19).Result()
	var history []Message
	for _, item := range data {
		var msg Message
		if json.Unmarshal([]byte(item), &msg) == nil {
			history = append(history, msg)
		}
	}
	// 反转：最老的在前（给 LLM 的上下文顺序正确）
	for i, j := 0, len(history)-1; i < j; i, j = i+1, j-1 {
		history[i], history[j] = history[j], history[i]
	}
	return history
}

// ============================================================================
// 情绪分析 — 参考 Transformers PreTrainedModel 抽象
// ============================================================================

type emotionKW struct {
	words []string
	label string
	prob  float64
	emoji string
	advice string
}

var emotionLexicon = []emotionKW{
	{[]string{"开心","高兴","快乐","棒","很好","谢谢","喜欢","爱","美好","幸福","欢欣","happy","great","wonderful","love","excited","joy","awesome"}, "positive", 0.85, "😊", "💖 保持好心情！记录让你开心的事。"},
	{[]string{"难过","伤心","痛苦","抑郁","崩溃","sad","hurt","depressed","crying","misery","heartbroken","心碎"}, "negative", 0.80, "💙", "💙 难过时，深呼吸。和信任的人聊聊会有帮助。"},
	{[]string{"焦虑","担心","害怕","紧张","不安","压力","恐惧","anxious","worried","scared","nervous","stress","fear","panic"}, "anxious", 0.78, "🌸", "🌸 焦虑时，试着做5次深呼吸，专注当下。"},
	{[]string{"生气","愤怒","讨厌","烦","火","暴躁","angry","hate","furious","mad","annoyed","rage","irritated"}, "angry", 0.82, "🤍", "🤍 愤怒是正常的。描述你的感受，而不是压抑它。"},
	{[]string{"哭泣","流泪","泪","sad","hurt","crying","tears","heartache","grief"}, "sad", 0.80, "😢", "😢 允许自己感受这些情绪，你值得被爱。"},
}

func analyzeEmotion(text string) EmotionResult {
	if text == "" {
		return EmotionResult{"neutral", 0.70, "🌿", "🌿 感谢分享，继续说吧。"}
	}
	textLower := text
	for _, e := range emotionLexicon {
		for _, kw := range e.words {
			if contains(textLower, kw) {
				return EmotionResult{e.label, e.prob, e.emoji, e.advice}
			}
		}
	}
	return EmotionResult{"neutral", 0.70, "🌿", "🌿 感谢分享，还有什么想聊的吗？"}
}

func contains(s, substr string) bool {
	if len(substr) > len(s) {
		return false
	}
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// ============================================================================
// 限流 — 简单 Token Bucket
// ============================================================================

type rateLimiter struct {
	mu       sync.Mutex
	tokens    float64
	lastRefill time.Time
	rate      float64 // tokens per second
	burst     float64
}

func newRateLimiter(rate, burst float64) *rateLimiter {
	return &rateLimiter{
		tokens:    burst,
		lastRefill: time.Now(),
		rate:      rate,
		burst:     burst,
	}
}

func (rl *rateLimiter) Allow() bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	elapsed := now.Sub(rl.lastRefill).Seconds()
	rl.lastRefill = now
	rl.tokens += elapsed * rl.rate
	if rl.tokens > rl.burst {
		rl.tokens = rl.burst
	}

	if rl.tokens >= 1 {
		rl.tokens--
		return true
	}
	return false
}

var limiter = newRateLimiter(10, 20) // 10 msg/s，burst 20

// ============================================================================
// Session ID — 密码学安全生成
// ============================================================================

func newSessionID() string {
	b := make([]byte, 16)
	fillRandom(b)
	return fmt.Sprintf("%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:16])
}

func fillRandom(b []byte) {
	// 使用 crypto/rand 的简化方式
	urandom, err := os.Open("/dev/urandom")
	if err != nil {
		// Fallback: 时间戳+随机
		seed := time.Now().UnixNano()
		for i := range b {
			b[i] = byte((seed >> (i % 8 * 4)) & 0xFF)
			seed = seed*1664525 + 1013904223
		}
		return
	}
	urandom.Read(b)
	urandom.Close()
}

// ============================================================================
// HTTP Handlers
// ============================================================================

func main() {
	initServices()
	r := gin.Default()

	r.Use(gin.Recovery())
	r.Use(corsMiddleware())

	// API routes
	r.POST("/api/chat", rateLimitMiddleware, handleChat)
	r.GET("/api/history/:session_id", handleHistory)
	r.DELETE("/api/history/:session_id", handleClearHistory)
	r.GET("/api/sessions", handleSessions)
	r.POST("/api/emotion/analyze", handleEmotionAnalyze)
	r.POST("/api/emotion/trend", handleEmotionTrend)

	// WebSocket
	r.GET("/ws/chat", handleWebSocket)

	// Health
	r.GET("/health", handleHealth)

	log.Println("[Gateway] listening on :8080")
	r.Run(":8080")
}

func corsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type,Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	}
}

func rateLimitMiddleware(c *gin.Context) {
	if !limiter.Allow() {
		c.JSON(429, gin.H{"error": "rate limit exceeded, please slow down"})
		c.Abort()
		return
	}
	c.Next()
}

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

	// 新建会话 or 复用
	if req.SessionID == "" {
		req.SessionID = newSessionID()
	}

	// 保存用户消息到 Redis
	userMsg, _ := json.Marshal(Message{
		Role:      "user",
		Content:   req.Message,
		Emotion:   req.Emotion,
		Timestamp: time.Now().UnixMilli(),
	})
	key := fmt.Sprintf("session:%s:messages", req.SessionID)
	rdb.LPush(ctx, key, string(userMsg))

	// 调度并等待响应（带超时）
	resp := scheduler.ScheduleChat(&req)
	c.JSON(200, resp)
}

func (s *Scheduler) ScheduleChat(req *ChatRequest) *ChatResponse {
	ch := make(chan *ChatResponse, 1)
	s.pendingMu.Lock()
	s.pendingOnce[req.SessionID] = ch
	s.pendingMu.Unlock()

	// 入队
	select {
	case s.pendingCh <- req:
	default:
		return &ChatResponse{
			SessionID:    req.SessionID,
			Message:      "请求积压，请稍后再试。",
			Emotion:      "neutral",
			EmotionProb:  0.7,
			Timestamp:    time.Now().UnixMilli(),
		}
	}

	// 等待，超时 30s
	select {
	case resp := <-ch:
		return resp
	case <-time.After(30 * time.Second):
		return &ChatResponse{
			SessionID:    req.SessionID,
			Message:      "抱歉，响应超时，请稍后再试。",
			Emotion:      "neutral",
			EmotionProb:  0.7,
			Timestamp:    time.Now().UnixMilli(),
		}
	}
}

func handleHistory(c *gin.Context) {
	sessionID := c.Param("session_id")
	key := fmt.Sprintf("session:%s:messages", sessionID)
	msgs, _ := rdb.LRange(ctx, key, 0, -1).Result()

	var history []Message
	for _, item := range msgs {
		var msg Message
		if json.Unmarshal([]byte(item), &msg) == nil {
			history = append(history, msg)
		}
	}
	for i, j := 0, len(history)-1; i < j; i, j = i+1, j-1 {
		history[i], history[j] = history[j], history[i]
	}
	c.JSON(200, gin.H{"session_id": sessionID, "messages": history})
}

func handleClearHistory(c *gin.Context) {
	sessionID := c.Param("session_id")
	key := fmt.Sprintf("session:%s:messages", sessionID)
	rdb.Del(ctx, key)
	c.JSON(200, gin.H{"ok": true})
}

func handleSessions(c *gin.Context) {
	keys, _ := rdb.Keys(ctx, "session:*:messages").Result()
	sessions := make([]gin.H, 0, len(keys))
	for _, key := range keys {
		msgs, _ := rdb.LRange(ctx, key, 0, 0).Result()
		title := "新对话"
		if len(msgs) > 0 {
			var msg Message
			if json.Unmarshal([]byte(msgs[0]), &msg) == nil {
				if len(msg.Content) > 25 {
					title = msg.Content[:25] + "..."
				} else {
					title = msg.Content
				}
			}
		}
		sessionID := key[len("session:") : len(key)-len(":messages")]
		sessions = append(sessions, gin.H{
			"session_id": sessionID,
			"title":      title,
		})
	}
	c.JSON(200, gin.H{"sessions": sessions})
}

func handleEmotionAnalyze(c *gin.Context) {
	var req struct{ Text string `json:"text"` }
	if err := c.ShouldBindJSON(&req); err != nil || req.Text == "" {
		c.JSON(400, gin.H{"error": "text is required"})
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

	// 主导情绪
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
	// 检查 Redis
	_, err := rdb.Ping(ctx).Result()
	redisOK := err == nil
	c.JSON(200, gin.H{
		"status":  "ok",
		"service": "gateway",
		"redis":   redisOK,
		"version": "1.0.0",
	})
}

// ============================================================================
// WebSocket Handler
// ============================================================================

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
}

func handleWebSocket(c *gin.Context) {
	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("[WS] upgrade error: %v", err)
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
				log.Printf("[WS] read error: %v", err)
			}
			break
		}

		var req ChatRequest
		if json.Unmarshal(msgBytes, &req) != nil {
			continue
		}
		req.SessionID = sessionID

		// 保存用户消息
		userMsg, _ := json.Marshal(Message{
			Role:      "user",
			Content:   req.Message,
			Timestamp: time.Now().UnixMilli(),
		})
		rdb.LPush(ctx, fmt.Sprintf("session:%s:messages", sessionID), string(userMsg))

		// 异步处理，WebSocket 推送结果
		go func(r ChatRequest) {
			resp := scheduler.ScheduleChat(&r)
			resp.SessionID = r.SessionID
			respJSON, _ := json.Marshal(resp)
			if err := conn.WriteMessage(websocket.TextMessage, respJSON); err != nil {
				log.Printf("[WS] write error: %v", err)
			}
		}(req)
	}
}

// ============================================================================
// Init
// ============================================================================

var rdb *redis.Client
var scheduler *Scheduler
var ctx = context.Background()

func initServices() {
	redisAddr := getEnv("REDIS_URL", "localhost:6379")
	if len(redisAddr) > 9 && redisAddr[:9] == "redis://" {
		redisAddr = redisAddr[9:]
	}

	rdb = redis.NewClient(&redis.Options{
		Addr:         redisAddr,
		DialTimeout:  5 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout:  3 * time.Second,
		PoolSize:     20,
	})

	// 测试 Redis 连接
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Printf("[Redis] connection failed: %v (will retry on requests)", err)
	} else {
		log.Printf("[Redis] connected to %s", redisAddr)
	}

	scheduler = NewScheduler()
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
