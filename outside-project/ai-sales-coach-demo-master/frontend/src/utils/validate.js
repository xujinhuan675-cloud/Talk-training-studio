/**
 * Created by PanJiaChen on 16/11/18.
 */

/**
 * @param {string} path
 * @returns {Boolean}
 */
export function isExternal(path) {
  return /^(https?:|mailto:|tel:)/.test(path)
}

/**
 * @param {string} str
 * @returns {Boolean}
 */
 export function validUsername(str) {
  const valid_map = ['admin', 'editor']
  return valid_map.indexOf(str.trim()) >= 0
}

/**
 * @param {string} //手机号
 * @returns {Boolean}
 */
 export function validPhone(phone) {
  if (!/^1(3|4|5|6|7|8)\d{9}$/.test(phone)) {
    return false;
  } else {
    return true;
  }
}

/**
 * @param {string} //座机 special plane 
 * @returns {Boolean}
 */
 export function validSpecialPlane(tel) {
  if (!/^\d{3}-\d{7,8}|\d{4}-\d{7,8}$/.test(tel)) {
    return false;
  } else {
    return true;
  }
}

/**
 * @param {string} //是否含有中文
 * @returns {Boolean}
 */
 export function validCn(text) {
  if (/[\u4E00-\u9FA5]/g.test(text)) {
    return false;
  } else {
    return true;
  }
}

/**
 * @param {string} //数字且只能包含一位小数就返回true
 * @returns {Boolean}
 */
 export function isNumber(text) {
   let val = Number(text)
   let reg = new RegExp("^\\d+(\\.\\d+)?$");
    if(val!== NaN && reg.test(val)){
        return true;
    }else{
        return false;
    }
}


/**
 *大小写字母
 */
 export function validateAlphabets(str){
	const reg = /^([A-Za-z]+)$/
	if (!reg.test(str)) {
		return false
	}
	return true
}
/**
 * 验正输入的是否为汉字
 */
 export function isChinese(num){
	const reg = /^[\u4e00-\u9fa5]{2,4}$/
	if (!reg.test(num)) {
		return false
	}
	return true
}

/**
 *
 * 验证输入中文、数字、特殊字符
 */
export function onpasteChines(num){
	const reg = /[^\0-9\u4E00-\u9FA5\-\_\ ]/g
	if (!reg.test(num)) {
		return false
	}
	return true
}
/**
 * 验正数字和英文和特殊字符
 */
 export function onpaste(num){
	const reg = /^[A-Za-z0-9_-\s ]+$/
	if (!reg.test(num)) {
		return false
	}
	return true
}
/**
 *
 * 验证数字、中文、英文、特殊字符
 */
 export function onpasteChinesEn(str){
	const reg = /[^\A-Za-z0-9\u4E00-\u9FA5\-\_\ ]/g
	if (!reg.test(str)) {
		return false
	}
	return true
}




