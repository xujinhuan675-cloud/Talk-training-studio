import API from '@/api'
import { getH5Token, setH5Token, removeH5Token, getH5User, setH5User } from '../../utils/auth'

const state = {
  token: getH5Token(),
  user: getH5User()
}

const mutations = {
  SET_TOKEN(state, token) {
    state.token = token
  },
  SET_USER(state, user) {
    state.user = user || {}
  },
  RESET(state) {
    state.token = ''
    state.user = {}
  }
}

const actions = {
  login({ commit }, payload) {
    return new Promise((resolve, reject) => {
      const data = { ...payload, pageType: 'xs' }
      API.login(data).then(response => {
        const d = response.data || {}
        const { token, name, role, group_id } = d
        const user = {
          name,
          role,
          group_id
        }
        setH5Token(token)
        setH5User(user)
        commit('SET_TOKEN', token)
        commit('SET_USER', user)
        resolve(response)
      }).catch(err => reject(err))
    })
  },
  logout({ commit }) {
    return new Promise(resolve => {
      removeH5Token()
      commit('RESET')
      resolve()
    })
  }
}

const getters = {
  token: state => state.token,
  user: state => state.user,
  userName: state => state.user.name || '',
  userRole: state => state.user.role || ''
}

export default {
  namespaced: true,
  state,
  mutations,
  actions,
  getters
}
