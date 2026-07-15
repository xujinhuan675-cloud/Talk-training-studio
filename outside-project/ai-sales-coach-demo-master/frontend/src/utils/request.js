import axios from 'axios'
import { Loading, Message } from 'element-ui'
import store from '@/store'
import { getToken } from '@/utils/auth'

//不加loading的接口
import apiWhiteList from '@/utils/apiWhiteList.js'

// let baseUrl = process.env.NODE_ENV !== 'development' ? '/' : 'https://mock.mengxuegu.com/mock/6119d8f55b12aa4b0b3ca9f9/example'
let baseUrl = process.env.NODE_ENV !== 'development' ? '/' : '/api'

//设置axios为form-data
// axios.defaults.headers.post['Content-Type'] = 'application/x-www-form-urlencoded';
// axios.defaults.headers.get['Content-Type'] = 'application/x-www-form-urlencoded';
import Qs from 'qs'
axios.defaults.transformRequest = [function (data) {
  if (data instanceof FormData) {
    //解决qs上传文件格式的会被过滤
    return data
  } else {
    //处理成formDate格式
    return Qs.stringify(data)
  }

}]

// 当前是否在 H5 子路由(hash 路径以 #/m/ 开头)
function isH5Route() {
  return typeof location !== 'undefined' && location.hash && location.hash.indexOf('#/m/') === 0
}
// H5 路径下走 Vant Toast(由 main.js 注入 window.__H5_SHOW_ERROR__),PC 路径仍走 Element Message
function showError(msg) {
  if (isH5Route() && typeof window.__H5_SHOW_ERROR__ === 'function') {
    window.__H5_SHOW_ERROR__(msg)
  } else {
    Message({ message: msg, type: 'error', duration: 3 * 1000 })
  }
}

// create an axios instance
const service = axios.create({
  // baseURL: process.env.VUE_APP_BASE_API, // url = base url + request url
  baseURL: baseUrl, // url = base url + request url
  // withCredentials: true, // send cookies when cross-domain requests
  // timeout: 5000 // request timeout
})
let loadinginstace
// request interceptor
let LOGINOUTFLAG = true;//登录过期弹框开关

let stepNum = 0;
//不加loading白名单
let whiteList = apiWhiteList;
service.interceptors.request.use(
  config => {

    // do something before request is sent
    // 仅在 H5 路径(#/m/*)下用 h5_token,PC 路径下用 PC 的 token,严格隔离防止 topCompany 串号
    const finalToken = isH5Route()
      ? (localStorage.getItem('h5_token') || getToken())
      : getToken()
    if (finalToken) {
      config.headers['Manage-Token'] = finalToken
    }
    if (whiteList.indexOf(config.url) == -1) {
      stepNum++;
      if (!loadinginstace) {
        loadinginstace = Loading.service({
          'fullscreen': true,
          'background': 'rgba(255, 255, 255, 0.4)',
          "customClass": "loadingXzindexTop"
        })
      }
    }
    return config
  },
  error => {
    if (loadinginstace && loadinginstace !== '') {
      loadinginstace.close();
    }
    // do something with request error
    console.log(error) // for debug
    return Promise.reject(error)
  }
)

// response interceptor
service.interceptors.response.use(

  response => {

    if (whiteList.indexOf(response.config.url.replace('/api', '')) == -1) {
      stepNum--;
    }
    if (stepNum <= 0) {
      if (loadinginstace && loadinginstace !== '') {
        loadinginstace.close();
      }
    }
    const res = response.data

    // if the custom code is not 20000, it is judged as an error.
    if (res.code === 20000) {
      //多个接口触发过期只弹一次
      if (LOGINOUTFLAG) {
        LOGINOUTFLAG = false;
        showError(res.message || '登录过期')
        store.dispatch('user/logout')
      }

    } else if (res.code !== 200) {
      showError(res.message || '数据异常，请联系客服')
      const err = new Error(res.message || 'Error')
      err.handled = true
      err.$interceptorHandled = true
      return Promise.reject(err)
    } else {
      return res
    }
  },
  error => {
    if (loadinginstace && loadinginstace !== '') {
      loadinginstace.close();
    }
    const msg = (error.message == 'Network Error' || error.message == 'Request failed with status code 500')
      ? '网络已断开，请检查您的网络'
      : error.message
    showError(msg)
    error.handled = true
    error.$interceptorHandled = true
    return Promise.reject(error)
  }
)

export default service
