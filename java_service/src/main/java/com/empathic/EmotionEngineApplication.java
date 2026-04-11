package com.empathic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;

import java.util.*;

@SpringBootApplication
public class EmotionEngineApplication {
    public static void main(String[] args) {
        SpringApplication.run(EmotionEngineApplication.class, args);
    }

    enum Emotion {
        POSITIVE("positive", "😊"),
        NEGATIVE("negative", "💙"),
        ANXIOUS("anxious", "🌸"),
        ANGRY("angry", "🤍"),
        SAD("sad", "😢"),
        NEUTRAL("neutral", "🌿");

        public final String label;
        public final String emoji;
        Emotion(String label, String emoji) { this.label = label; this.emoji = emoji; }
    }

    static class EmotionClassifier {
        private static final Map<String, Emotion> LEXICON = new HashMap<>();
        static {
            // @Primary 正面
            for (String w : List.of("开心","高兴","快乐","棒","很好","谢谢","喜欢","爱","美好","幸福","happy","great","wonderful","love","excited","joy","awesome"))
                LEXICON.put(w, Emotion.POSITIVE);
            // @Secondary 负面
            for (String w : List.of("难过","伤心","痛苦","抑郁","绝望","崩溃","sad","hurt","depressed","devastated","crying","misery","heartbroken"))
                LEXICON.put(w, Emotion.NEGATIVE);
            // @Anxiety
            for (String w : List.of("焦虑","担心","害怕","紧张","不安","压力","恐惧","anxious","worried","scared","nervous","stress","fear","panic"))
                LEXICON.put(w, Emotion.ANXIOUS);
            // @Anger
            for (String w : List.of("生气","愤怒","讨厌","烦","火","气死了","暴躁","angry","hate","furious","mad","annoyed","rage"))
                LEXICON.put(w, Emotion.ANGRY);
            // @Sad
            for (String w : List.of("难过","伤心","痛苦","哭泣","泪","心酸","sad","hurt","crying","tears","heartache","grief"))
                LEXICON.put(w, Emotion.SAD);
        }

        public static Map<String,Object> classify(String text) {
            if (text == null || text.isBlank()) {
                return Map.of("emotion","neutral","prob",0.70,"emoji","🌿","advice","感谢分享，还有什么想聊的吗？");
            }
            String lower = text.toLowerCase();
            Map<Emotion, Integer> scores = new EnumMap<>(Emotion.class);
            for (var e : LEXICON.entrySet()) {
                if (lower.contains(e.getKey().toLowerCase())) {
                    scores.merge(e.getValue(), 1, Integer::sum);
                }
            }
            Emotion maxE = Emotion.NEUTRAL;
            int maxS = 0;
            for (var e : scores.entrySet()) {
                if (e.getValue() > maxS) { maxS = e.getValue(); maxE = e.getKey(); }
            }
            double prob = Math.min(0.99, 0.55 + maxS * 0.08);
            return Map.of(
                "emotion", maxE.label,
                "prob", prob,
                "emoji", maxE.emoji,
                "advice", getAdvice(maxE.label)
            );
        }

        private static String getAdvice(String e) {
            return switch(e) {
                case "positive" -> "💖 保持好心情！记录让你开心的事。";
                case "negative" -> "💙 难过时，深呼吸。和信任的人聊聊会有帮助。";
                case "anxious" -> "🌸 焦虑时，试着做5次深呼吸。";
                case "angry" -> "🤍 愤怒是正常的。描述感受，而非压抑。";
                case "sad" -> "😢 允许自己感受这些情绪，你值得被爱。";
                default -> "🌿 感谢分享，还有什么想聊的吗？";
            };
        }
    }

    @RestController
    public static class EmotionController {
        @PostMapping("/analyze")
        public ResponseEntity<Map<String,Object>> analyze(@RequestBody Map<String,String> body) {
            String text = body.get("text");
            if (text == null || text.isBlank()) {
                return ResponseEntity.badRequest().body(Map.of("error","text is required"));
            }
            return ResponseEntity.ok(EmotionClassifier.classify(text));
        }

        @GetMapping("/health") 
        public ResponseEntity<Map<String,String>> health() {
            return ResponseEntity.ok(Map.of("status","ok","service","emotion-engine"));
        }
    }
}
