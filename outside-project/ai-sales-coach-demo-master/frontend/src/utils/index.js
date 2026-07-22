/**
 * Created by PanJiaChen on 16/11/18.
 */

import moment from 'moment';

import base64 from '@/utils/base64';
import CryptoJS from 'crypto-js';
/**
 * Parse the time to string
 * @param {(Object|string|number)} time
 * @param {string} cFormat
 * @returns {string | null}
 */
export function parseTime(time, cFormat) {
  if (arguments.length === 0 || !time) {
    return null
  }
  const format = cFormat || '{y}-{m}-{d} {h}:{i}:{s}'
  let date
  if (typeof time === 'object') {
    date = time
  } else {
    if ((typeof time === 'string')) {
      if ((/^[0-9]+$/.test(time))) {
        // support "1548221490638"
        time = parseInt(time)
      } else {
        // support safari
        // https://stackoverflow.com/questions/4310953/invalid-date-in-safari
        time = time.replace(new RegExp(/-/gm), '/')
      }
    }

    if ((typeof time === 'number') && (time.toString().length === 10)) {
      time = time * 1000
    }
    date = new Date(time)
  }
  const formatObj = {
    y: date.getFullYear(),
    m: date.getMonth() + 1,
    d: date.getDate(),
    h: date.getHours(),
    i: date.getMinutes(),
    s: date.getSeconds(),
    a: date.getDay()
  }
  const time_str = format.replace(/{([ymdhisa])+}/g, (result, key) => {
    const value = formatObj[key]
    // Note: getDay() returns 0 on Sunday
    if (key === 'a') { return ['日', '一', '二', '三', '四', '五', '六'][value] }
    return value.toString().padStart(2, '0')
  })
  return time_str
}

/**
 * @param {number} time
 * @param {string} option
 * @returns {string}
 */
export function formatTime(time, option) {
  if (('' + time).length === 10) {
    time = parseInt(time) * 1000
  } else {
    time = +time
  }
  const d = new Date(time)
  const now = Date.now()

  const diff = (now - d) / 1000

  if (diff < 30) {
    return '刚刚'
  } else if (diff < 3600) {
    // less 1 hour
    return Math.ceil(diff / 60) + '分钟前'
  } else if (diff < 3600 * 24) {
    return Math.ceil(diff / 3600) + '小时前'
  } else if (diff < 3600 * 24 * 2) {
    return '1天前'
  }
  if (option) {
    return parseTime(time, option)
  } else {
    return (
      d.getMonth() +
      1 +
      '月' +
      d.getDate() +
      '日' +
      d.getHours() +
      '时' +
      d.getMinutes() +
      '分'
    )
  }
}

/**
 * @param {string} url
 * @returns {Object}
 */
export function param2Obj(url) {
  const search = decodeURIComponent(url.split('?')[1]).replace(/\+/g, ' ')
  if (!search) {
    return {}
  }
  const obj = {}
  const searchArr = search.split('&')
  searchArr.forEach(v => {
    const index = v.indexOf('=')
    if (index !== -1) {
      const name = v.substring(0, index)
      const val = v.substring(index + 1, v.length)
      obj[name] = val
    }
  })
  return obj
}


/**
 * 获得字符串实际长度，中文2，英文1
 */
export function getTextWidth(str) {
  var realLength = 0
  var len = str.length
  var charCode = -1
  for (var i = 0; i < len; i++) {
    charCode = str.charCodeAt(i)
    if (charCode >= 0 && charCode <= 128) realLength += 1
    else realLength += 2
  }
  return realLength
}




/**
 * @param {string} type 类型
 * @returns {Array}
 */
//获取指定时间范围
export function getDate(type) {
  var startTime = '';
  var endTime = '';
  //今日
  if (type == 'today') {
    startTime = moment(moment().valueOf()).format('YYYY-MM-DD');
    endTime = moment(moment().valueOf()).format('YYYY-MM-DD');
  }
  //今日-月底
  if (type == 'todayMonth') {
    startTime = moment(moment().valueOf()).format('YYYY-MM-DD');
    endTime = moment(moment().month(moment().month()).endOf('month').valueOf()).format('YYYY-MM-DD');
  }
  //本周
  if (type == 'week') {
    startTime = moment(new Date()).isoWeekday(1).format('YYYY-MM-DD');
    endTime = moment(moment().valueOf()).format('YYYY-MM-DD');
  }
  //昨日
  if (type == 'yesterday') {
    startTime = moment(moment().add(-1, 'days').startOf('day').valueOf()).format('YYYY-MM-DD');
    endTime = moment(moment().add(-1, 'days').endOf('day').valueOf()).format('YYYY-MM-DD');
  }
  //上月
  if (type == 'lastMonth') {
    startTime = moment(moment().month(moment().month() - 1).startOf('month').valueOf()).format('YYYY-MM-DD');
    endTime = moment(moment().month(moment().month() - 1).endOf('month').valueOf()).format('YYYY-MM-DD');

  }
  //本月
  if (type == 'thisMonth') {
    startTime = moment(moment().month(moment().month()).startOf('month').valueOf()).format('YYYY-MM-DD');
    endTime = moment(moment().valueOf()).format('YYYY-MM-DD'); //不能到未来日期

  }
  //前15天（包含今天）
  if (type == 'before15') {
    // 获取当前时间
    const now = moment();
    // 计算15天前的开始时间（00:00:00）
    const startDate = now.clone().subtract(15, 'days').startOf('day');

    // 计算15天前的结束时间（23:59:59）
    const endDate = now.clone().subtract(0, 'days').endOf('day');
    startTime = startDate.format('YYYY-MM-DD');
    endTime = endDate.format('YYYY-MM-DD');
  }
  return [startTime, endTime]
}


//获取文字宽度

export function getStringWidth(text, font) {
  // 创建一个canvas元素用于测量文本
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');

  // 设置字体样式
  context.font = font || '20px Arial';

  // 测量文本
  const metrics = context.measureText(text);

  // 返回文本宽度
  return metrics.width;
}



// 引入后可直接调用：
// import { getCurrentTime } from '@/utils/date';
// console.log(getCurrentTime().day); // 年月日
// console.log(getCurrentTime().timer); // 时分秒
// console.log(getCurrentTime().timestamp); // 时间戳
export function getCurrentTime() {
  const now = moment();
  return {
    // 获取年月日（格式：YYYY-MM-DD）
    get day() {
      return now.format('YYYY-MM-DD');
    },
    // 获取时分秒（格式：HH:mm:ss）
    get timer() {
      return now.format('HH:mm:ss');
    },
    // 获取完整日期时间（格式：YYYY-MM-DD HH:mm:ss）
    get full() {
      return now.format('YYYY-MM-DD HH:mm:ss');
    },
    // 获取时间戳（毫秒）
    get timestamp() {
      return now.valueOf();
    },
    // 获取时间戳（秒）
    get timestampSec() {
      return now.unix();
    },
    // 获取时间戳（秒）
    get day2() {
      return now.format('YYYY.MM.DD');
    }
  };
};



/**
 * 生成TaskId
 * @returns {number}
 */
export const generateTaskId = () => {
  return new Date().getTime() * 10000 + parseInt(Math.random() * 10000, 10)
}


/**
 * 当前会话列表的 聊天的时间显示
 * @param {*} time
 */
export function transformTime(time) {
  const nt = Number(time)
  const date = new Date(nt)
  const h = date.getHours()
  const m = date.getMinutes()
  if (time > currentDay) {
    if (m < 10) {
      return h + ':0' + m
    } else {
      return h + ':' + m
    }
  } else if (time > currentDay - 24 * 60 * 60 * 1000) {
    return '昨天'
  } else {
    const month = date.getMonth() + 1
    const day = date.getDate()
    return `${month}月${day}日`
  }
}


/**
 * 获取消息的内容
 * @param {Object} talk 消息
 * @param {Boolean} isBease64 是否需要解密
 */
export function getContent(talk, isBease64 = true) {
  const { ContentType, Content } = talk
  if (!Content) {
    return ''
  }
  const digest = isBease64 ? base64.decode(Content) : Content;

  if (ContentType === 'Text' || ContentType === '1') {
    if (talk.FriendId && talk.FriendId.indexOf('chatroom') > 0) {
      return unescape(escape(digest.replace(/.*?:/, '')).replace('%0A', '%20')).replace(' ', '')
    }
    return digest
  }
  if (ContentType === 'System') {
    return digest
  }
  const contentMap = {
    Picture: '[图片]',
    2: '[图片]',
    Voice: '[语音]',
    3: '[语音]',
    Video: '[视频]',
    4: '[视频]',
    // System: '[系统消息]',
    // 5: '[系统消息]',
    Link: '[链接]',
    6: '[链接]',
    LinkExt: '[扩展的链接消息]',
    7: '[扩展的链接消息]',
    File: '[文件]',
    8: '[文件]',
    NameCard: '[名片]',
    9: '[名片]',
    Location: '[位置消息]',
    10: '[位置消息]',
    LuckyMoney: '[红包]',
    11: '[红包]',
    MoneyTrans: '[转账]',
    12: '[转账]',
    WeApp: '[小程序]',
    13: '[小程序]',
    Emoji: '[动画表情]',
    14: '[动画表情]',
    Sys_LuckyMoney: '[红包系统消息]',
    16: '[红包系统消息]',
    RoomSystem: '[群系统消息]',
    17: '[群系统消息]',
    NotifyMsg: '[系统通知]',
    21: '[系统通知]',
    ShiPinHao: '[视频号]',
    24: '[视频号]',
    PaiYiPai: '[拍一拍]',
    26: '[拍一拍]'
  }
  return contentMap[ContentType] || ContentType
}


export function getFileIcon(fileName) {
  // 后缀名 → 图标文件名 映射表（可根据你的需求扩展）
  const iconMap = {
    xls: 'exl.png',
    xlsx: 'exl.png',
    gif: 'gif.png',
    jpg: 'jpg.png',
    jpeg: 'jpg.png',
    png: 'jpg.png',
    mp3: 'mp3.png',
    pdf: 'pdf.png',
    ppt: 'ppt.png',
    pptx: 'ppt.png',
    txt: 'txt.png',
    doc: 'wold.png',
    docx: 'wold.png',
    zip: 'zip.png',
    rar: 'zip.png',
    '7z': 'zip.png'
  }

  // 处理空文件名/非字符串的边界情况
  if (!fileName || typeof fileName !== 'string') {
    return 'https://daqiangui-web.oss-cn-shanghai.aliyuncs.com/statics/aiChat/images/fileIcon/default.png'
  }

  // 核心：提取最后一个小数点后的后缀（兼容多小数点、点开头/结尾）
  const lastDotIndex = fileName.lastIndexOf('.');
  let ext = '';
  // 确保小数点不是最后一位，且不是文件名的第一个字符（如 .gitignore 不算有后缀）
  if (lastDotIndex > 0 && lastDotIndex < fileName.length - 1) {
    ext = fileName.slice(lastDotIndex + 1).toLowerCase();
  }

  // 匹配图标，无匹配则用默认
  const iconName = iconMap[ext] || 'default.png';
  // 替换为你实际的图标路径
  return `https://daqiangui-web.oss-cn-shanghai.aliyuncs.com/statics/aiChat/images/fileIcon/${iconName}`;
}


//首字母变大写
export function capitalizeFirst(str) {
  // 边界处理：空值、非字符串直接返回原数据，避免报错
  if (!str || typeof str !== 'string') return str;
  // 核心逻辑：首字母大写 + 剩余字符保持原样
  return str.charAt(0).toUpperCase() + str.slice(1);
}

export const getMd5ByTimestampAndRandom = () => {
  const timestamp = Date.now();
  const randomNum = Math.floor(Math.random() * 90000) + 10000;
  return CryptoJS.MD5(timestamp + '' + randomNum).toString();
};

export function formatDisplayTime(targetTime) {
  let targetTimestamp;
  if (typeof targetTime === 'number') {
    targetTimestamp = targetTime;
  } else {
    const timeStr = targetTime.replace(/-/g, '/');
    targetTimestamp = new Date(timeStr).getTime();
  }
  if (isNaN(targetTimestamp)) {
    return '';
  }
  const currentTimestamp = Date.now();
  const timeDiff = Math.floor((currentTimestamp - targetTimestamp) / 1000);
  if (timeDiff < 86400) {
    const date = new Date(targetTimestamp);
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
  } else if (timeDiff < 259200) {
    return '3天内';
  } else if (timeDiff < 604800) {
    return '7天内';
  } else {
    const date = new Date(targetTimestamp);
    const year = date.getFullYear();
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
}