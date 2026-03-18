/** Axios API client — attaches JWT from localStorage to every request. */

import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// When any request returns 401 the stored token has expired or is invalid.
// Clear it and reload so the user is sent back to the login page.
apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (
      typeof error === 'object' &&
      error !== null &&
      'response' in error &&
      (error as { response?: { status?: number } }).response?.status === 401
    ) {
      localStorage.removeItem('token')
      window.location.reload()
    }
    return Promise.reject(error)
  },
)

export default apiClient
