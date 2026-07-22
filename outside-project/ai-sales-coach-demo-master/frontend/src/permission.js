import router from './router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { getToken } from '@/utils/auth'

NProgress.configure({ showSpinner: false })

const whiteList = ['/login']

router.beforeEach((to, from, next) => {
  NProgress.start()
  document.title = (to.meta && to.meta.title) ? `${to.meta.title} - AI销冠陪练中心` : 'AI销冠陪练中心'

  // H5 独立鉴权（h5_token）
  if (to.meta && to.meta.isH5) {
    const h5Token = localStorage.getItem('h5_token')
    if (h5Token) {
      to.path === '/m/login' ? next('/m/challenge') : next()
    } else {
      to.path === '/m/login' ? next() : next(`/m/login?redirect=${encodeURIComponent(to.fullPath)}`)
    }
    NProgress.done()
    return
  }

  // PC 鉴权
  const hasToken = getToken()
  if (hasToken) {
    if (to.path === '/login') {
      next({ path: '/' })
      return
    }
    if (to.path === '/training/config' && localStorage.getItem('role') !== 'admin') {
      next({ path: '/training/challenge' })
      return
    }
    next()
  } else {
    whiteList.includes(to.path) ? next() : next(`/login?redirect=${to.path}`)
  }
})

router.afterEach(() => {
  NProgress.done()
})
