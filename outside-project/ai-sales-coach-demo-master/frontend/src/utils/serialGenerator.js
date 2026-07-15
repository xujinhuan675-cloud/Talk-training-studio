// 采用闭包+单例模式，确保全局唯一实例，避免状态丢失
const SerialGenerator = (() => {
  class Generator {
    constructor() {
      this.lastTimestamp = 0; // 上一次生成的时间戳
      this.sequence = 0; // 同一毫秒内的序列号
      this.sequenceMax = 999; // 序列号最大值（3位，支持同一毫秒1000个）
    }

    // 生成20位唯一流水号：时间戳(13位) + 序列号(3位) + 随机数(4位)
    generate() {
      let timestamp = Date.now();

      // 处理时钟回拨（极少情况）：若当前时间戳小于上次，强制使用上次时间戳
      if (timestamp < this.lastTimestamp) {
        console.warn('时钟回拨，使用上次时间戳避免重复');
        timestamp = this.lastTimestamp;
      }

      // 同一毫秒内，序列号自增
      if (timestamp === this.lastTimestamp) {
        this.sequence++;
        // 序列号超出最大值时，等待到下一毫秒（确保不重复）
        if (this.sequence > this.sequenceMax) {
          // 循环等待至下一毫秒
          while (timestamp <= this.lastTimestamp) {
            timestamp = Date.now();
          }
          this.sequence = 0; // 重置序列号
        }
      } else {
        // 不同毫秒，重置序列号
        this.sequence = 0;
      }

      // 更新上次时间戳
      this.lastTimestamp = timestamp;

      // 拼接各部分并补零（确保长度）
      const timeStr = timestamp.toString().padStart(13, '0'); // 13位时间戳
      const sequenceStr = this.sequence.toString().padStart(3, '0'); // 3位序列号
      const randomStr = Math.floor(Math.random() * 10000).toString().padStart(4, '0'); // 4位随机数

      const serial = timeStr + sequenceStr + randomStr;

      // 严格校验长度（20位）
      if (serial.length !== 20) {
        throw new Error(`流水号长度错误：${serial}（长度${serial.length}）`);
      }

      return serial;
    }
  }

  // 闭包内创建唯一实例，外部无法创建新实例
  const instance = new Generator();
  return {
    generate: () => instance.generate()
  };
})();

export default SerialGenerator;