import API from '@/api'
import { getToken, setToken, removeToken } from '@/utils/auth'
import { resetRouter } from '@/router'

const getDefaultState = () => ({
  token: getToken(),
  name: localStorage.getItem('name') || '',
  role: localStorage.getItem('role') || 'staff',
  groupId: localStorage.getItem('group_id') || null,
})

const state = getDefaultState()

const mutations = {
  SET_TOKEN: (state, { token, name, role, group_id }) => {
    state.token = token
    state.name = name
    state.role = role
    state.groupId = group_id
    localStorage.setItem('name', name)
    localStorage.setItem('role', role)
    localStorage.setItem('group_id', group_id || '')
  },
  RESET_STATE: (state) => {
    Object.assign(state, getDefaultState())
  },
}

const actions = {
  login({ commit }, userInfo) {
    return API.login(userInfo).then(res => {
      if (res.code !== 200) throw new Error(res.message || '登录失败')
      const d = res.data
      setToken(d.token)
      commit('SET_TOKEN', d)
    })
  },

  getInfo({ commit }) {
    return API.getUserInfo().then(res => {
      if (res.code !== 200) throw new Error(res.message)
      const d = res.data
      commit('SET_TOKEN', { token: getToken(), name: d.name, role: d.role, group_id: d.group_id })
    })
  },

  logout({ commit }) {
    removeToken()
    resetRouter()
    commit('RESET_STATE')
    localStorage.removeItem('name')
    localStorage.removeItem('role')
    localStorage.removeItem('group_id')
  },

  resetToken({ commit }) {
    removeToken()
    commit('RESET_STATE')
  }
}

const getters = {}

export default {
  namespaced: true,
  state,
  mutations,
  actions,
  getters
}
