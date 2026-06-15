import { create } from 'zustand'
import { api } from '../api/client'
import { clearAuthSession, getAuthToken, getAuthUsername, setAuthSession } from '../api/authToken'

interface AuthState {
  token: string | null
  username: string | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: getAuthToken(),
  username: getAuthUsername(),
  isAuthenticated: Boolean(getAuthToken()),
  login: async (username, password) => {
    const response = await api.post('/auth/login', { username, password })
    const token = response.data.token as string
    const loggedInUsername = response.data.username as string
    setAuthSession(token, loggedInUsername)
    set({ token, username: loggedInUsername, isAuthenticated: true })
  },
  logout: async () => {
    const token = get().token
    if (token) {
      try {
        await api.post('/auth/logout')
      } catch {
        // 本地退出优先，忽略服务端已重启/令牌已失效等情况。
      }
    }
    clearAuthSession()
    set({ token: null, username: null, isAuthenticated: false })
  },
}))
