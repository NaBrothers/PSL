import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('psl_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => {
    if (res.config.method && res.config.method !== 'get') {
      window.dispatchEvent(new Event('psl-status-update'))
    }
    return res
  },
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('psl_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
