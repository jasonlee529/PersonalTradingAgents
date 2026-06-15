const TOKEN_KEY = 'pta_auth_token'
const USERNAME_KEY = 'pta_auth_username'

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getAuthUsername() {
  return localStorage.getItem(USERNAME_KEY)
}

export function setAuthSession(token: string, username: string) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USERNAME_KEY, username)
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USERNAME_KEY)
}
