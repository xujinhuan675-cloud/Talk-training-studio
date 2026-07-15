import request from '@/utils/request'
import training from './training.js'

const auth = {
  login(data) {
    return request({ url: '/Client/login', method: 'post', data })
  },
  getUserInfo(data) {
    return request({ url: '/Client/getUserInfo', method: 'post', data })
  }
}

const API = Object.assign({}, auth, training)

export default API
