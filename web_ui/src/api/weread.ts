import http from './http'

// 注意：后端 API 前缀为 API_BASE=/api/v1/wx（见 core/base.py），
// 前端 baseURL=api/v1/，因此这里所有路径必须带 /wx 前缀，
// 与 auth.ts / user.ts 等其他模块保持一致（上游 main 分支漏加，已修复）。

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

/** 探测宿主机已安装浏览器（配置页下拉用） */
export async function getWereadBrowsers() {
    return http.get('/wx/weread/browsers')
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

/** 清除 Cookie */
export async function clearWereadCookie() {
    return http.delete('/wx/weread/cookie')
}

// ---- 扫码授权 ----

/** 获取微信读书扫码登录二维码 */
export async function getWereadQrCode() {
    return http.get('weread/qr/code')
}

/** 检查微信读书扫码登录状态 */
export async function checkWereadQrStatus() {
    return http.get('weread/qr/status')
}

/** 完成微信读书扫码登录 */
export async function completeWereadQrLogin() {
    return http.get('weread/qr/over')
}
