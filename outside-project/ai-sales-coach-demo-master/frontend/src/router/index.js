import Vue from 'vue'
import Router from 'vue-router'

Vue.use(Router)

import Layout from '@/layout'

export const constantRoutes = [
  {
    path: '/login',
    component: () => import('@/views/login/index'),
    hidden: true
  },
  // H5
  {
    path: '/m/login',
    component: () => import('@/h5/views/login/index.vue'),
    hidden: true,
    meta: { isH5: true, hideTab: true, title: '登录' }
  },
  {
    path: '/m/history/detail',
    component: () => import('@/h5/views/history/detail.vue'),
    hidden: true,
    meta: { isH5: true, hideTab: true, title: '练习详情' }
  },
  {
    path: '/m',
    component: () => import('@/h5/layout/index.vue'),
    redirect: '/m/challenge',
    hidden: true,
    meta: { isH5: true },
    children: [
      { path: 'challenge', component: () => import('@/h5/views/challenge/index.vue'), meta: { isH5: true, keepAlive: true, title: '闯关陪练' } },
      { path: 'history', component: () => import('@/h5/views/history/index.vue'), meta: { isH5: true, keepAlive: true, title: '练习记录' } },
      { path: 'leaderboard', component: () => import('@/h5/views/leaderboard/index.vue'), meta: { isH5: true, keepAlive: true, title: '排行榜' } },
      { path: 'profile', component: () => import('@/h5/views/profile/index.vue'), meta: { isH5: true, title: '我的' } }
    ]
  },
  // PC
  {
    path: '/',
    component: Layout,
    redirect: '/training/challenge',
    children: [
      { path: 'training/challenge', name: 'TrainingChallenge', component: () => import('@/views/pages/training/challenge/index'), meta: { title: '闯关陪练', icon: 'icon-peilianzhongxin' } },
      { path: 'training/result', name: 'TrainingResult', component: () => import('@/views/pages/training/result/index'), meta: { title: '演练结果', noCache: true }, hidden: true },
      { path: 'training/replay', name: 'TrainingReplay', component: () => import('@/views/pages/training/replay/index'), meta: { title: '回放', noCache: true }, hidden: true },
      { path: 'training/history', name: 'TrainingHistory', component: () => import('@/views/pages/training/history/index'), meta: { title: '练习记录', icon: 'icon-lianxijilu' } },
      { path: 'training/leaderboard', name: 'TrainingLeaderboard', component: () => import('@/views/pages/training/leaderboard/index'), meta: { title: '销冠榜', icon: 'icon-xiaoguan' } },
      { path: 'training/config', name: 'TrainingConfig', component: () => import('@/views/pages/training/config/index'), meta: { title: '陪练配置', icon: 'icon-peilianzhongxin' } }
    ]
  },
  { path: '*', redirect: '/training/challenge', hidden: true }
]

const createRouter = () => new Router({
  scrollBehavior: () => ({ y: 0 }),
  routes: constantRoutes
})

const router = createRouter()

export function resetRouter() {
  const newRouter = createRouter()
  router.matcher = newRouter.matcher
}

export default router
