const TokenKey = 'h5_token'
const UserKey = 'h5_user'

export function getH5Token() {
  return localStorage.getItem(TokenKey)
}

export function setH5Token(token) {
  localStorage.setItem(TokenKey, token)
}

export function removeH5Token() {
  localStorage.removeItem(TokenKey)
  localStorage.removeItem(UserKey)
}

export function getH5User() {
  try {
    return JSON.parse(localStorage.getItem(UserKey) || '{}')
  } catch (e) {
    return {}
  }
}

export function setH5User(user) {
  localStorage.setItem(UserKey, JSON.stringify(user || {}))
}
