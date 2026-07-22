const TokenKey = 'token'

export function getToken() {
  return localStorage.getItem(TokenKey);
}

export function setToken(token) {
  return localStorage.setItem(TokenKey, token);
}

export function removeToken() {
  //保留会话记录
  let conversationListData = localStorage.getItem('conversationListData');
  window.localStorage.clear();
  if(conversationListData){
    localStorage.setItem('conversationListData',conversationListData);
  }
}
export function getStorage(key) {
  return localStorage.getItem(key);
}
export function setStorage(key) {
  return localStorage.setItem(key);
}

export function removeStorage(key) {
  return localStorage.removeItem(key);
}
