/**
 * Created by zhaoshanshan on 2020/6/5
 */
/* 邮箱 */
const email = /^(\w-*\.*)+@(\w-?)+(\.\w{2,})+$/

/* 手机格式 */
const telephone = /^1\d{10}$/

/* 固话格式(待区号) */
const phone = /^0\d{2,3}-\d{7,8}$/

/* 合法uri*/
const validateURL = /^(https?|ftp):\/\/([a-zA-Z0-9.-]+(:[a-zA-Z0-9.&%$-]+)*@)*((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]?)(\.(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])){3}|([a-zA-Z0-9-]+\.)*[a-zA-Z0-9-]+\.(com|edu|gov|int|mil|net|org|biz|arpa|info|name|pro|aero|coop|museum|[a-zA-Z]{2}))(:[0-9]+)*(\/($|[a-zA-Z0-9.,?'\\+&%$#=~_-]+))*$/

/* 小写字母*/
const validateLowerCase = /^[a-z]+$/

/* 大写字母*/
const validateUpperCase = /^[A-Z]+$/

/* 大小写字母*/
const validateAlphabets = /^[A-Za-z]+$/

// validate email
const validateEmail = /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/

/* 身份证 */
const idCard = /^[1-9]\d{7}((0\d)|(1[0-2]))(([0|1|2]\d)|3[0-1])\d{3}$|^[1-9]\d{5}[1-9]\d{3}((0\d)|(1[0-2]))(([0|1|2]\d)|3[0-1])\d{3}([0-9]|X)$/

/** 大于0正整数*/
const validateInteger = /^[1-9]\d*$/

/* 只能输入字母、数字 */
const only_num_char = /^[0-9a-zA-Z]+$/

const website = /^((https|http|ftp|rtsp|mms){0,1}(:\/\/){0,1})www\.(([A-Za-z0-9-~]+)\.)+([A-Za-z0-9-~\/])+$/

/* 只能输入正数字 */
const onlyNum = /\D/

/* 只匹配数字与小数点 */
const onlyNumberDouble = /^\d+(\.{0,1}\d+$|$)/

/** 大于0切小数点不超过两位*/
const validateTwoDecimalPlace = /(^[1-9](\d+)?(\.\d{1,2})?$)|(^\d\.\d{1,2}$)/

/** 大于0切小数点不超过三位*/
const validateThreeDecimalPlace = /(^[1-9](\d+)?(\.\d{1,3})?$)|(^\d\.\d{1,3}$)/


/** 是否含有中午*/
const validateCnPlace = /[\u4E00-\u9FA5]/g

//8到16位数字与字母组合
const alidatePassword = /^(?![0-9]+$)(?![a-zA-Z]+$)[0-9A-Za-z]{8,16}$/;



const validate = {
	only_num_char,
	validateURL,
	validateLowerCase,
	validateUpperCase,
	validateAlphabets,
	validateEmail,
	idCard,
	validateInteger,
	validateTwoDecimalPlace,
	validateThreeDecimalPlace,
	onlyNum,
	onlyNumberDouble,
	telephone,
	phone,
	website,
	email,
	validateCnPlace,
	alidatePassword
}
export default validate
