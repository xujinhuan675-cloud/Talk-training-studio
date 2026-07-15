/**
 * H5 voice input mixin.
 * Uses the browser Web Speech API so the portfolio demo does not depend on
 * a server-side speech recognition endpoint.
 */
export default {
  data() {
    const SpeechRecognition = typeof window !== 'undefined'
      ? (window.SpeechRecognition || window.webkitSpeechRecognition)
      : null

    return {
      speechSupported: !!SpeechRecognition,
      recording: false,
      recognizing: false,
      voiceRecognition: null
    }
  },
  beforeDestroy() {
    this.stopRecord()
  },
  methods: {
    startRecord() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
      if (!SpeechRecognition) {
        this.$toast({ message: '当前浏览器不支持语音输入，请使用新版 Chrome 或 Edge', duration: 2500 })
        return
      }
      if (this.recording || this.recognizing) return

      const recognition = new SpeechRecognition()
      recognition.lang = 'zh-CN'
      recognition.interimResults = true
      recognition.continuous = false

      const originalText = this.composerText || ''
      let finalText = ''

      recognition.onresult = event => {
        let interimText = ''
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const text = event.results[i][0].transcript
          if (event.results[i].isFinal) finalText += text
          else interimText += text
        }
        this.composerText = `${originalText}${finalText}${interimText}`.trim()
      }

      recognition.onerror = event => {
        this.recording = false
        this.recognizing = false
        this.voiceRecognition = null
        const msg = event && event.error === 'not-allowed'
          ? '麦克风权限未授权'
          : '语音输入失败，请改用键盘输入'
        this.$toast({ message: msg, duration: 2500 })
      }

      recognition.onend = () => {
        this.recording = false
        this.recognizing = false
        this.voiceRecognition = null
      }

      this.voiceRecognition = recognition
      this.recording = true
      this.recognizing = true
      recognition.start()
    },

    stopRecord() {
      if (this.voiceRecognition) {
        try { this.voiceRecognition.stop() } catch (e) { /* noop */ }
      }
      this.recording = false
      this.recognizing = false
      this.voiceRecognition = null
    }
  }
}
