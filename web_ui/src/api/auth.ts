import http from './http'
import axios from 'axios'
export interface LoginParams {
  username: string
  password: string
}

export interface LoginResult {
  access_token: string
  token_type: string
}

export const login = (data: LoginParams) => {
  const formData = new URLSearchParams()
  formData.append('username', data.username)
  formData.append('password', data.password)
  return http.post<LoginResult>('/wx/auth/login', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
  })
}

export interface VerifyResult {
  is_valid: boolean
  username: string
  expires_at?: number
}

export const verifyToken = () => {
  return http.get<VerifyResult>('/wx/auth/verify')
}
export const QRCode = () => {
  return new Promise((resolve, reject) => {
    http.get('/wx/auth/qr/code').then(res => {
      const intervalId = setInterval(() => {
        axios.head(res?.code).then(response => {
          if(response.status==200){
            console.log(response)
            clearInterval(intervalId)
            resolve(res)
          }
        }).catch(err => {
          // clearInterval(intervalId)
          // reject(err)
        })
      }, 3000)
    }).catch(reject)
  })
}
export const checkQRCodeStatus = () => {
  return new Promise((resolve, reject) => {
    const intervalId = setInterval(() => {
        http.get("wx/auth/qr/status").then(response => {
          if(response?.login_status){
            clearInterval(intervalId)
            resolve(response)
          }
        }).catch(err => {
          // clearInterval(intervalId)
          // reject(err)
        })
      }, 3000)
  })
}
export const refreshToken = () => {
  return http.post<LoginResult>('/wx/auth/refresh')
}

export const logout = () => {
  return http.post('/wx/auth/logout')
}

export const getCurrentUser = () => {
  return http.get('/wx/user')
}