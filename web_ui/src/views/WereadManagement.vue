<template>
  <div class="weread-management">
    <a-card title="微信读书管理" :bordered="false">
      <!-- Cookie 配置区域 -->
      <a-divider orientation="left">连接配置</a-divider>
      <a-alert v-if="connectionStatus === 'loading'" type="info" :show-icon="false">
        <template #icon><icon-loading /></template>
        正在测试连接...
      </a-alert>
      <a-alert v-else-if="connectionStatus === 'success'" type="success">
        <template v-if="isWereadMp">
          公众号采集连接成功，共检测到 {{ articleCount }} 篇文章
        </template>
        <template v-else>
          连接成功！书架共 {{ bookCount }} 本书，用户 VID: {{ vid }}
        </template>
      </a-alert>
      <a-alert v-else-if="connectionStatus === 'error'" type="error">
        连接失败：{{ errorMsg }}
      </a-alert>
      <a-alert v-if="managedByConfig" type="warning" style="margin-top: 12px">
        部分凭据由 config.yaml 或环境变量管理，页面不会覆盖这些值。
      </a-alert>

      <!-- 多账号列表 -->
      <a-divider orientation="left">微信账号（{{ accountCount }} 个）</a-divider>
      <a-alert type="info" style="margin-bottom: 12px">
        配额按微信账号独立计算。账号 A 的配额用尽时会自动切到账号 B 继续采集，
        所以多绑几个微信号可显著提升采集成功率。点击「扫码授权」可继续添加，
        同一个微信号重复扫码只会更新它的 Cookie，不会重复添加。
      </a-alert>
      <a-spin :loading="loadingAccounts">
        <a-empty
          v-if="!loadingAccounts && accounts.length === 0"
          description="尚未绑定微信账号，点击下方「扫码授权」添加第一个"
        />
        <a-list v-else :data="accounts" :bordered="false" style="margin-bottom: 12px">
          <a-list-item v-for="acc in accounts" :key="acc.vid || acc.index">
            <a-list-item-meta>
              <template #title>
                <a-space>
                  <a-tag :color="acc.is_primary ? 'arcoblue' : 'gray'">
                    第 {{ acc.index }} 个微信
                  </a-tag>
                  <span>{{ acc.name }}</span>
                  <a-tag v-if="acc.is_primary" color="green" size="small">主账号</a-tag>
                  <a-tooltip v-if="acc.is_primary" content="主账号用于连接测试与状态显示；配额耗尽时会自动切到其他账号">
                    <icon-question-circle />
                  </a-tooltip>
                </a-space>
              </template>
              <template #description>
                VID: {{ acc.vid || '未知' }} · Cookie {{ acc.cookie_masked || '—' }}
                <template v-if="acc.has_ticket"> · 有 ticket</template>
              </template>
            </a-list-item-meta>
            <template #extra>
              <a-button
                size="mini"
                status="danger"
                :loading="removingVid === acc.vid"
                :disabled="managedByConfig || (accountCount <= 1 && acc.is_primary)"
                @click="removeAccount(acc)"
              >
                移除
              </a-button>
            </template>
          </a-list-item>
        </a-list>
      </a-spin>

      <a-form :model="cookieForm" layout="vertical" style="margin-top: 16px">
        <a-form-item label="微信读书 Cookie" field="cookie" :extra="accountCount > 1 ? `当前编辑主账号（第 1 个微信）。粘贴另一个微信号的 Cookie 可新增账号；同一 VID 会覆盖更新。也可直接用「扫码授权」。` : '从浏览器 weread.qq.com 页面按 F12 → Network 标签 → 任意请求 → Request Headers 中复制完整 Cookie 值'">
          <a-textarea
            v-model="cookieForm.cookie"
            placeholder="粘贴完整的 Cookie 字符串，需包含 wr_vid、wr_skey 等关键字段"
            :auto-size="{ minRows: 3, maxRows: 6 }"
            allow-clear
            :disabled="cookieManagedByConfig"
          />
        </a-form-item>
        <a-form-item label="x-wr-ticket（兼容旧版）" field="ticket" extra="当前版本通常可留空；仅旧版接口要求时填写">
          <a-input-password
            v-model="cookieForm.ticket"
            placeholder="通常可留空；仅旧版接口要求时填写"
            allow-clear
            :disabled="ticketManagedByConfig"
          />
        </a-form-item>
        <a-form-item label="用户名称（可选）" field="name">
          <a-input v-model="cookieForm.name" placeholder="如：张三" />
        </a-form-item>
        <a-divider style="margin: 8px 0">自动刷新 Cookie（可选，定时任务前自动更新）</a-divider>
        <a-form-item label="公众号主页 URL" field="cookie_refresh_url" extra="用于自动刷新 Cookie。请填公众号主页（reader 页，形如 https://weread.qq.com/web/mp/reader/xxxx），不要填带 bookId 的 /web/mp/articles 接口地址">
          <a-input v-model="cookieForm.cookie_refresh_url" placeholder="https://weread.qq.com/web/mp/reader/MP_WXS_xxx" />
        </a-form-item>
        <a-form-item label="浏览器路径（本机 Chrome）" field="browser_path" extra="本机 Chrome 可执行文件路径，用于打开上方 URL 提取 Cookie；留空则用 Playwright 自带 Chromium">
          <a-input v-model="cookieForm.browser_path" placeholder="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" />
        </a-form-item>
        <a-space>
          <a-button type="primary" @click="saveCookie" :loading="saving">
            <template #icon><icon-save /></template>
            保存 Cookie
          </a-button>
          <a-button type="outline" status="success" @click="showQrAuth">
            <template #icon><icon-scan /></template>
            {{ accountCount > 0 ? '扫码授权（添加账号）' : '扫码授权' }}
          </a-button>
          <a-button @click="testConnection" :loading="testing">
            <template #icon><icon-check-circle /></template>
            测试连接
          </a-button>
          <a-button status="danger" @click="clearCookieHandler" :disabled="!hasConfig || managedByConfig">
            <template #icon><icon-delete /></template>
            清除 Cookie
          </a-button>
          <a-button @click="saveConfig" :loading="savingConfig">
            <template #icon><icon-settings /></template>
            保存刷新配置
          </a-button>
        </a-space>
      </a-form>

      <!-- 书架区域 -->
      <a-divider v-if="!isWereadMp" orientation="left">我的书架</a-divider>
      <a-spin v-if="!isWereadMp" :loading="loadingBookshelf" tip="加载书架...">
        <div v-if="bookshelf.length === 0 && !loadingBookshelf" class="empty-bookshelf">
          <a-empty description="书架上暂无书籍，请先连接微信读书" />
        </div>
        <div v-else class="bookshelf-grid">
          <div
            v-for="book in bookshelf"
            :key="book.book_id"
            class="book-card"
          >
            <div class="book-cover">
              <img v-if="book.cover" :src="book.cover" :alt="book.title" />
              <div v-else class="book-cover-placeholder">
                <icon-book />
              </div>
            </div>
            <div class="book-info">
              <div class="book-title">{{ book.title }}</div>
              <div class="book-author">{{ book.author }}</div>
              <div class="book-meta">
                <a-tag v-if="book.progress > 0" color="blue">
                  阅读 {{ book.progress }}%
                </a-tag>
                <a-tag v-if="book.finishedDate" color="green">已读完</a-tag>
              </div>
              <a-button
                size="mini"
                type="outline"
                @click="collectBookNotes(book)"
                :loading="collectingBookId === book.book_id"
                style="margin-top: 8px"
              >
                采集笔记
              </a-button>
            </div>
          </div>
        </div>
      </a-spin>

      <!-- 采集全部按钮 -->
      <div v-if="!isWereadMp && bookshelf.length > 0" style="margin-top: 16px">
        <a-button
          type="primary"
          @click="collectAllNotes"
          :loading="collectingAll"
        >
          <template #icon><icon-upload /></template>
          采集全部书籍笔记
        </a-button>
      </div>
    </a-card>

    <!-- 采集进度弹窗 -->
    <a-modal v-model:visible="collectModalVisible" title="采集结果" :footer="false" :width="500">
      <a-result
        :status="collectResult.status"
        :title="collectResult.title"
      >
        <template #subtitle>{{ collectResult.subtitle }}</template>
      </a-result>
    </a-modal>

    <!-- 扫码授权弹窗 -->
    <WereadAuthQrcode
      ref="wereadQrRef"
      :account-count="accountCount"
      @success="handleWereadQrSuccess"
      @cancel="handleWereadQrCancel"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, inject } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  getWereadStatus,
  saveWereadCookie,
  saveWereadConfig,
  testWereadConnection,
  testWereadMpConnection,
  getWereadBookshelf,
  collectWereadNotes,
  clearWereadCookie,
} from '@/api/weread'
import WereadAuthQrcode from '@/components/WereadAuthQrcode.vue'

// 状态
const connectionStatus = ref<'idle' | 'loading' | 'success' | 'error'>('idle')
const bookCount = ref(0)
const articleCount = ref(0)
const vid = ref('')
const errorMsg = ref('')
const saving = ref(false)
const savingConfig = ref(false)
const testing = ref(false)
const hasConfig = ref(false)

// 多账号（配额按微信账号独立计算，耗尽时自动切换）
interface WereadAccount {
  index: number
  vid: string
  name: string
  cookie_masked: string
  has_ticket: boolean
  is_primary: boolean
}
const accounts = ref<WereadAccount[]>([])
const accountCount = ref(0)
const loadingAccounts = ref(false)
const removingVid = ref('')
const isWereadMp = ref(false)
const managedByConfig = ref(false)
const cookieManagedByConfig = ref(false)
const ticketManagedByConfig = ref(false)
const loadingBookshelf = ref(false)
const collectingBookId = ref('')
const collectingAll = ref(false)
const collectModalVisible = ref(false)

// 表单
const cookieForm = reactive({
  cookie: '',
  ticket: '',
  name: '',
  cookie_refresh_url: '',
  browser_path: '',
  browser_type: 'chrome',
})

// 书架
interface Book {
  book_id: string
  title: string
  author: string
  cover: string
  intro: string
  progress: number
  finishedDate: number
}
const bookshelf = ref<Book[]>([])

// 扫码授权
const wereadQrRef = ref()

// 扫码成功后同步刷新 App 顶栏的微信读书授权状态（由 App.vue provide）
const refreshWereadStatus = inject('refreshWereadStatus') as (() => Promise<void>) | undefined

function showQrAuth() {
  wereadQrRef.value?.startAuth()
}

async function handleWereadQrSuccess(result: any) {
  const prevCount = accountCount.value
  // 扫码成功后刷新状态（后端会返回完整账号列表）
  await loadStatus()
  await testConnection()
  // 同步顶栏图标状态，避免 header 仍显示"未授权"
  if (refreshWereadStatus) {
    await refreshWereadStatus()
  }
  const vid = result?.vid || ''
  if (accountCount.value > prevCount) {
    Message.success(`已添加第 ${accountCount.value} 个微信账号（VID: ${vid}），配额耗尽时将自动切换`)
  } else {
    Message.success(`微信读书授权成功，用户 VID: ${vid}`)
  }
}

function handleWereadQrCancel() {
  // 用户取消扫码，无需额外处理
}

// 采集结果
const collectResult = reactive({
  status: 'success' as 'success' | 'error',
  title: '',
  subtitle: '',
})

// 初始化
onMounted(async () => {
  await loadStatus()
})

async function loadStatus() {
  loadingAccounts.value = true
  try {
    const data = await getWereadStatus() as any
    hasConfig.value = data.configured
    // 多账号列表（后端对旧格式做了归一化，前端无需区分是否已迁移）
    accounts.value = Array.isArray(data.accounts) ? data.accounts : []
    accountCount.value = typeof data.account_count === 'number'
      ? data.account_count
      : accounts.value.length
    isWereadMp.value = data.gather_model === 'weread_mp'
    managedByConfig.value = data.managed_by_config
    cookieManagedByConfig.value = data.cookie_managed_by_config
    ticketManagedByConfig.value = data.ticket_managed_by_config
    if (data.vid) {
      vid.value = data.vid
      cookieForm.name = data.name || ''
    }
    // 回显已保存的凭据到输入框，便于查看/编辑（后端已按用户要求返回完整值）
    if (data.has_cookie) {
      cookieForm.cookie = data.cookie || ''
    }
    if (data.has_ticket) {
      cookieForm.ticket = data.ticket || ''
    }
    // 回显自动刷新配置
    cookieForm.cookie_refresh_url = data.cookie_refresh_url || ''
    cookieForm.browser_path = data.browser_path || ''
    cookieForm.browser_type = data.browser_type || 'chrome'
  } catch (e) {
    // 忽略
  } finally {
    loadingAccounts.value = false
  }
}

async function saveCookie() {
  if (!cookieForm.cookie.trim() && !hasConfig.value) {
    Message.warning('首次配置请填写 Cookie')
    return
  }
  saving.value = true
  try {
    const res = await saveWereadCookie(
      cookieForm.cookie || undefined,
      '',
      cookieForm.name,
      cookieForm.ticket || undefined,
    ) as any
    hasConfig.value = true
    // 后端返回最新账号列表：新增账号时明确告知是「第 N 个微信」
    if (Array.isArray(res?.accounts)) {
      accounts.value = res.accounts
      accountCount.value = res.account_count ?? res.accounts.length
    }
    if (res?.action === 'added') {
      Message.success(`已添加第 ${res.account_count} 个微信账号，配额耗尽时将自动切换`)
    } else {
      Message.success(`凭据已保存，当前共 ${accountCount.value} 个微信账号`)
    }
    await loadStatus()
    await testConnection()
  } catch (e: any) {
    Message.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function saveConfig() {
  savingConfig.value = true
  try {
    await saveWereadConfig({
      cookie_refresh_url: cookieForm.cookie_refresh_url,
      browser_path: cookieForm.browser_path,
      browser_type: cookieForm.browser_type,
    })
    Message.success('自动刷新配置已保存')
  } catch (e: any) {
    Message.error(e?.message || '保存配置失败')
  } finally {
    savingConfig.value = false
  }
}

async function testConnection() {
  testing.value = true
  connectionStatus.value = 'loading'
  try {
    if (isWereadMp.value) {
      const result = await testWereadMpConnection() as any
      articleCount.value = result.article_count
    } else {
      const result = await testWereadConnection() as any
      bookCount.value = result.book_count
      vid.value = result.vid
      await loadBookshelf()
    }
    connectionStatus.value = 'success'
  } catch (e: any) {
    connectionStatus.value = 'error'
    errorMsg.value = typeof e === 'string' ? e : e?.message || '连接失败'
  } finally {
    testing.value = false
  }
}

async function loadBookshelf() {
  loadingBookshelf.value = true
  try {
    const data = await getWereadBookshelf() as any
    bookshelf.value = data.books || []
  } catch (e: any) {
    Message.error(e?.message || '获取书架失败')
  } finally {
    loadingBookshelf.value = false
  }
}

async function clearCookie() {
  // 有多个账号时明确区分：移除单个 vs 清空全部
  const isMulti = accountCount.value > 1
  const tip = isMulti
    ? `确定要清除全部 ${accountCount.value} 个微信账号吗？此操作不可恢复。建议改为逐个「移除」。`
    : '确定要清除该微信账号的 Cookie 吗？'
  if (!window.confirm(tip)) return
  try {
    const res = await clearWereadCookie() as any
    Message.success(isMulti ? '全部账号已清除' : 'Cookie 已清除')
    accounts.value = []
    accountCount.value = 0
    hasConfig.value = false
    connectionStatus.value = 'idle'
    bookshelf.value = []
    bookCount.value = 0
    if (res?.accounts) {
      accounts.value = res.accounts
      accountCount.value = res.account_count ?? res.accounts.length
    }
  } catch (e: any) {
    Message.error(e?.message || '清除失败')
  }
}

// 移除单个账号（保留其它账号，便于下线某个微信号）
async function removeAccount(acc: WereadAccount) {
  if (!window.confirm(`确定移除「${acc.name}」（VID ${acc.vid}）吗？`)) return
  removingVid.value = acc.vid
  try {
    const res = await clearWereadCookie(acc.vid) as any
    accounts.value = res?.accounts || []
    accountCount.value = res?.account_count ?? accounts.value.length
    hasConfig.value = accountCount.value > 0
    Message.success(res?.message || `已移除，剩余 ${accountCount.value} 个账号`)
    if (accountCount.value > 0) {
      // 主账号可能已变（移除的是第一项），重新拉一次状态回显
      await loadStatus()
    }
  } catch (e: any) {
    Message.error(e?.message || '移除失败')
  } finally {
    removingVid.value = ''
  }
}

function getBookMpId(book: Book): string {
  return `WEREAD_${book.book_id}`
}

async function collectBookNotes(book: Book) {
  collectingBookId.value = book.book_id
  try {
    const result = await collectWereadNotes({
      mp_id: getBookMpId(book),
      mp_name: book.title,
      faker_id: book.book_id,
    }) as any

    collectResult.status = 'success'
    collectResult.title = `《${book.title}》采集完成`
    collectResult.subtitle = `共采集 ${result.collected} 条笔记`
    collectModalVisible.value = true
    Message.success(`《${book.title}》采集完成，共 ${result.collected} 条笔记`)
  } catch (e: any) {
    collectResult.status = 'error'
    collectResult.title = '采集失败'
    collectResult.subtitle = typeof e === 'string' ? e : e?.message || '未知错误'
    collectModalVisible.value = true
    Message.error(typeof e === 'string' ? e : '采集失败')
  } finally {
    collectingBookId.value = ''
  }
}

async function collectAllNotes() {
  collectingAll.value = true
  try {
    const result = await collectWereadNotes({
      mp_id: 'WEREAD_ALL',
      mp_name: '微信读书全部笔记',
    }) as any

    collectResult.status = 'success'
    collectResult.title = '全部书籍采集完成'
    collectResult.subtitle = `共采集 ${result.collected} 条笔记`
    collectModalVisible.value = true
    Message.success(`全部采集完成，共 ${result.collected} 条笔记`)
  } catch (e: any) {
    collectResult.status = 'error'
    collectResult.title = '全部采集失败'
    collectResult.subtitle = typeof e === 'string' ? e : e?.message || '未知错误'
    collectModalVisible.value = true
    Message.error(typeof e === 'string' ? e : '采集失败')
  } finally {
    collectingAll.value = false
  }
}
</script>

<style scoped>
.weread-management {
  padding: 16px;
}

.bookshelf-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.book-card {
  display: flex;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  transition: box-shadow 0.2s;
}

.book-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.book-cover {
  width: 80px;
  height: 110px;
  flex-shrink: 0;
  border-radius: 4px;
  overflow: hidden;
  background: var(--color-fill-2);
}

.book-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.book-cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: var(--color-text-3);
}

.book-info {
  flex: 1;
  min-width: 0;
}

.book-title {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 4px;
}

.book-author {
  font-size: 12px;
  color: var(--color-text-3);
  margin-bottom: 4px;
}

.book-meta {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.empty-bookshelf {
  padding: 40px 0;
}
</style>
