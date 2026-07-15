function encode(str) {
  try {
    return btoa(
      encodeURIComponent(str).replace(/%([0-9A-F]{2})/g, function(match, p1) {
        return String.fromCharCode('0x' + p1);
      })
    );
  } catch (e) {
    console.error('Base64 编码失败:', e);
    throw e; // 抛出错误让调用方处理
  }
}

function decode(str) {
  try {
    // 清理无效字符（仅保留 Base64 允许的字符）
    const base64Str = str.replace(/[^A-Za-z0-9+/=]/g, '');
    // 补充填充字符使长度为 4 的倍数
    const padding = base64Str.length % 4;
    if (padding) {
      const add = 4 - padding;
      base64Str += '='.repeat(add);
    }
    return decodeURIComponent(
      atob(base64Str)
        .split('')
        .map(function(c) {
          return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        })
        .join('')
    );
  } catch (e) {
    console.error('Base64 解码失败:', e);
    throw e; // 抛出错误让调用方处理
  }
}

export default {
  encode,
  decode
};