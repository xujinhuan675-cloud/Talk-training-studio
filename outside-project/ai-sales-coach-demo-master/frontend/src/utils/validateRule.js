/**
 * 公共表单验证
 */
 import validate from './validateData'

 /**
  * 值为数字正整数 可为空
  */
 
 var onlyNumNoDouble = (rule, value, callback) => {
   if (!value || value === '') {
     callback()
   } else {
     if (validate.onlyNum.test(value)) {
       callback(new Error('请输数字'))
       return false
     }
     callback()
   }
 }
 /**
  * 值为数字 可为空
  */
 
 var onlyNum = (rule, value, callback) => {
   if (!value || value === '') {
     callback()
   } else {
     if (validate.onlyNum.test(value)) {
       callback(new Error('请输数字'))
       return false
     }
 
     callback()
   }
 }
 
 /**
  * 值为数字包含负数 可为空
  */
 
 var onlyNumFu = (rule, value, callback) => {
   if (!value || value === '') {
     callback()
   } else {
     if (validate.onlyNumberDouble.test(value)) {
       callback(new Error('请输数字2'))
       return false
     }
 
     callback()
   }
 }
 
 var validateMonth = (rule, value, callback) => {
   var pattern = new RegExp("[`~!@#$^&*()=|{}':;',\\[\\].<>《》/?~！@#￥……&*（）——|{}【】‘；：”“'。，、？%]")
   var patternTwo = new RegExp('[A-Z]+')
   var patternThree = new RegExp('[a-z]+')
   if (!value) {
     callback()
   } else if (!/^[^\u4e00-\u9fa5]+$/.test(value)) {
     callback(new Error('请输入数字'))
   } else if (pattern.test(value)) {
     callback(new Error('请输入数字'))
   } else if (patternTwo.test(value)) {
     callback(new Error('请输入数字'))
   } else if (patternThree.test(value)) {
     callback(new Error('请输入数字'))
   }
   callback()
 }
 
 /**
  * 保留两位小数点 数值可以为空
  */
 
 var twoDecimalPlacesRules = (rule, value, callback) => {
   var num = ''
   if (String(value).indexOf(',') > 0) {
     num = Number(value.replace(/,/g, ''))
   } else {
     num = Number(value)
   }
   if (!value || value === '') {
     callback()
   } else {
     if (Number(num) < 0 || Number(num) === 0 || !validate.onlyNumberDouble.test(parseInt(num))) {
       callback(new Error('请输大于0的数字'))
       return false
     }
     if (!validate.validateTwoDecimalPlace.test(num)) {
       callback(new Error('请输入数字,最多2位小数'))
     }
     callback()
   }
 }
 
 /**
  * 保留两位小数点 数值不能为空
  */
 
 var twoDecimalPlacesRulesRequire = (rule, value, callback) => {
   var num = ''
   if (String(value).indexOf(',') > 0) {
     num = Number(value.replace(/,/g, ''))
   } else {
     num = Number(value)
   }
   if (!value || value === '') {
     callback(new Error('请输入'))
   } else {
     if (Number(num) < 0 || Number(num) === 0 || !validate.onlyNumberDouble.test(parseInt(num))) {
       callback(new Error('请输大于0的数字'))
       return false
     }
     if (!validate.validateTwoDecimalPlace.test(num)) {
       callback(new Error('请输入数字,最多2位小数'))
     }
 
     callback()
   }
 }
 
 // 同时校验手机号与固定电话
 var checkPhone = (rule, value, callback) => {
   var telephone = validate.telephone
   if(value == ''){
    callback(new Error('请输入'));
  }
   else if (!telephone.test(value)) {
    callback(new Error('请输入正确的手机号'));
  }else{
    callback();
  }
 }

 // 同校验银行卡号
 var checkBank = (rule, value, callback) => {
  var bank = /^[1-9]\d{9,29}$/
  if(value == ''){
    callback(new Error('请输入'));
  }
  else if (!bank.test(value)) {
   callback(new Error('请输入正确的银行卡号'));
 }else{
   callback();
 }
}
 
 // 邮箱
 var checkEmail = (rule, value, callback) => {
   var email = validate.email
   if (!value) {
     callback(new Error('请输入'))
    //  callback()
   } else {
     if (!email.test(value)) {
       callback(new Error('请输入正确的邮箱格式'))
     }
 
     callback()
   }
 }

 //校验是否包含中文
var checkCn = (rule, value, callback) => {
  var validateCnPlace = validate.validateCnPlace
  if (!value) {
    // callback(new Error('请输入'))
    if(rule.required){
      callback(new Error('请输入'))
    }else{
      callback()
    }
    
  } else {
    if (validateCnPlace.test(value)) {
      callback(new Error('不能输入中文'))
    }
    callback()
  }
}


// 密码
var checkPassword = (rule, value, callback) => {
  var alidatePassword = validate.alidatePassword
  if (!value) {
    if(rule.required){
      callback(new Error('请输入'))
    }else{
      callback()
    }
   //  callback()
  } else {
    if (!alidatePassword.test(value)) {
      callback(new Error('请输入8到16位数字与字母组合'))
    }

    callback()
  }
}

 
 const validateRule = {
   twoDecimalPlacesRules,
   twoDecimalPlacesRulesRequire,
   onlyNumNoDouble,
   onlyNum,
   onlyNumFu,
   validateMonth,
   checkPhone,
   checkEmail,
   checkCn,
   checkPassword,
   checkBank
 }
 export default validateRule
 