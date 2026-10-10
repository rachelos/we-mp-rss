import http from './http'

// 注意：后端 API 前缀为 API_BASE=/api/v1/wx（见 core/base.py），
// 前端 baseURL=api/v1/，因此这里所有路径必须带 /wx 前缀，
// 与 auth.ts / user.ts 等其他模块保持一致（上游 main 分支漏加，已修复）。
//
// 通道区分：本模块为【微信读书】通道，扫码 API 走 /wx/weread/qr/*；
// 【微信公众号】通道的扫码 API 走 /wx/auth/qr/*（见 auth.ts），两者相互独立。

/** 获取微信读书配置状态 */
export async function getWereadStatus() {
    return http.get('/wx/weread')
}

/** 保存微信读书 Cookie */
export async function saveWereadCookie(cookie?: string, vid?: string, name?: string, ticket?: string) {
    return http.post('/wx/weread/cookie', { cookie, vid, name, ticket })
}

/** 保存 Cookie 自动刷新配置（公众号文章 URL + 本机浏览器路径） */
export async function saveWereadConfig(params: {
    cookie_refresh_url?: string
    browser_path?: string
    browser_type?: string
}) {
    return http.post('/wx/weread/config', params)
}

/** 测试连接 */
export async function testWereadConnection() {
    return http.post('/wx/weread/test')
}

/** 测试微信读书公众号列表凭据 */
export async function testWereadMpConnection(mpId?: string) {
    return http.post('/wx/weread/mp/test', { mp_id: mpId || '' })
}

/** 获取书架列表 */
export async function getWereadBookshelf() {
    return http.post('/wx/weread/bookshelf')
}

/** 手动采集笔记 */
export async function collectWereadNotes(params: {
    mp_id: string
    mp_name?: string
    faker_id?: string
    max_page?: number
    gather_content?: boolean
}) {
    return http.post('/wx/weread/collect', params)
}

/**
 * 清除 Cookie
 * - 传 vid：只清除该微信账号（保留其它账号）
 * - 不传：清除全部账号（清空凭据，保留刷新配置）
 */
export async function clearWereadCookie(vid?: string) {
    return http.delete('/wx/weread/cookie', { params: vid ? { vid } : {} })
}

// ---- 扫码授权 ----

/** 获取微信读书扫码登录二维码（微信读书通道，区别于公众号 /wx/auth/qr/*） */
export async function getWereadQrCode() {
    return http.get('/wx/weread/qr/code')
}

/** 检查微信读书扫码登录状态（微信读书通道，区别于公众号 /wx/auth/qr/*） */
export async function checkWereadQrStatus() {
    return http.get('/wx/weread/qr/status')
}

/** 完成微信读书扫码登录（微信读书通道，区别于公众号 /wx/auth/qr/*） */
export async function completeWereadQrLogin() {
    return http.get('/wx/weread/qr/over')
}
