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
        连接成功！书架共 {{ bookCount }} 本书，用户 VID: {{ vid }}<span v-if="hasTicket">；公众号采集凭据已验证</span>
      </a-alert>
      <a-alert v-else-if="connectionStatus === 'error'" type="error">
        连接失败：{{ errorMsg }}
      </a-alert>
      <a-alert v-if="managedByConfig" type="warning" style="margin-top: 12px">
        部分凭据由 config.yaml 或环境变量管理，页面不会覆盖这些值。
      </a-alert>

      <a-form :model="cookieForm" layout="vertical" style="margin-top: 16px">
        <a-form-item label="微信读书 Cookie" field="cookie" extra="从浏览器 weread.qq.com 页面按 F12 → Network 标签 → 任意请求 → Request Headers 中复制完整 Cookie 值">
          <a-textarea
            v-model="cookieForm.cookie"
            placeholder="粘贴完整的 Cookie 字符串，需包含 wr_vid、wr_skey 等关键字段"
            :auto-size="{ minRows: 3, maxRows: 6 }"
            allow-clear
            :disabled="cookieManagedByConfig"
          />
        </a-form-item>
        <a-form-item label="x-wr-ticket（公众号采集）" field="ticket" extra="仅 weread_mp 模式需要：从 /web/mp/articles 请求的 Request Headers 复制">
          <a-input-password
            v-model="cookieForm.ticket"
            placeholder="粘贴 x-wr-ticket；只采集书籍笔记时可留空"
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
        <a-form-item label="本机浏览器" field="browser_path" extra="选择用于打开微信读书提取 Cookie 的浏览器，系统自动探测安装路径并填入；留空则用 Playwright 自带 Chromium">
          <a-select
            v-model="browserSelect"
            placeholder="选择浏览器（自动探测安装路径）"
            @change="onBrowserChange"
            allow-clear
          >
            <a-option
              v-for="b in browserOptions"
              :key="b.key"
              :value="b.key"
            >
              {{ b.name }}{{ b.path ? '（已安装）' : '（未安装）' }}{{ b.supported ? '' : '（暂未支持）' }}
            </a-option>
            <a-option value="custom">自定义（手动输入路径）</a-option>
          </a-select>
          <div v-if="browserSelect === 'custom'" style="margin-top: 8px">
            <a-input v-model="cookieForm.browser_path" placeholder="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" />
          </div>
          <a-alert v-if="agentOffline" type="warning" :show-icon="false" style="margin-top: 8px">
            宿主刷新代理未运行，无法自动探测浏览器，请手动输入路径或先启动代理。
          </a-alert>
        </a-form-item>
        <a-space>
          <a-button type="primary" @click="saveCookie" :loading="saving">
            <template #icon><icon-save /></template>
            保存 Cookie
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
      <a-divider orientation="left">我的书架</a-divider>
      <a-spin :loading="loadingBookshelf" tip="加载书架...">
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
      <div style="margin-top: 16px" v-if="bookshelf.length > 0">
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  getWereadStatus,
  saveWereadCookie,
  saveWereadConfig,
  getWereadBrowsers,
  testWereadConnection,
  testWereadMpConnection,
  getWereadBookshelf,
  collectWereadNotes,
  clearWereadCookie,
} from '@/api/weread'

// 状态
const connectionStatus = ref<'idle' | 'loading' | 'success' | 'error'>('idle')
const bookCount = ref(0)
const vid = ref('')
const errorMsg = ref('')
const saving = ref(false)
const savingConfig = ref(false)
const testing = ref(false)
const hasConfig = ref(false)
const hasTicket = ref(false)
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

// 采集结果
const collectResult = reactive({
  status: 'success' as 'success' | 'error',
  title: '',
  subtitle: '',
})

// 浏览器下拉（自动探测）
interface BrowserOption {
  key: string
  name: string
  type: string
  supported: boolean
  path: string
}
const browserOptions = ref<BrowserOption[]>([])
const browserSelect = ref('custom')
const agentOffline = ref(false)

// 初始化
onMounted(async () => {
  await loadStatus()
  await loadBrowsers()
})

async function loadBrowsers() {
  try {
    const data = await getWereadBrowsers() as any
    agentOffline.value = !!data.agent_offline
    browserOptions.value = (data.browsers || []).map((b: any) => ({
      key: b.key,
      name: b.name,
      type: b.type,
      supported: b.supported,
      path: b.path || '',
    }))
    // 回显：已保存路径与某个已安装浏览器一致 → 选中该浏览器，否则回退自定义
    const savedPath = cookieForm.browser_path
    if (savedPath) {
      const hit = browserOptions.value.find((b) => b.path && b.path === savedPath)
      browserSelect.value = hit ? hit.key : 'custom'
    } else {
      browserSelect.value = 'custom'
    }
  } catch (e) {
    agentOffline.value = true
  }
}

function onBrowserChange(val: string | number | undefined) {
  const key = val === undefined || val === null ? '' : String(val)
  if (!key || key === 'custom') {
    browserSelect.value = 'custom'
    return
  }
  const b = browserOptions.value.find((x) => x.key === key)
  if (!b) return
  if (!b.supported) {
    Message.error(`${b.name} 暂未支持自动刷新（当前仅 Chromium 内核浏览器可用），请选择其他浏览器或自定义`)
    browserSelect.value = 'custom'
    return
  }
  if (!b.path) {
    Message.error(`未检测到 ${b.name} 的安装路径，配置失败；请先安装该浏览器或选择其他浏览器`)
    browserSelect.value = 'custom'
    return
  }
  cookieForm.browser_path = b.path
  cookieForm.browser_type = b.type
  Message.success(`已自动填入 ${b.name} 路径`)
}

async function loadStatus() {
  try {
    const data = await getWereadStatus() as any
    hasConfig.value = data.configured
    hasTicket.value = data.has_ticket
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
  }
}

async function saveCookie() {
  if (!cookieForm.cookie.trim() && !hasConfig.value) {
    Message.warning('首次配置请填写 Cookie')
    return
  }
  saving.value = true
  try {
    await saveWereadCookie(
      cookieForm.cookie || undefined,
      '',
      cookieForm.name,
      cookieForm.ticket || undefined,
    )
    Message.success('微信读书凭据保存成功')
    hasConfig.value = true
    if (cookieForm.ticket || ticketManagedByConfig.value) {
      hasTicket.value = true
    }
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
    const result = await testWereadConnection() as any
    if (hasTicket.value) {
      await testWereadMpConnection()
    }
    connectionStatus.value = 'success'
    bookCount.value = result.book_count
    vid.value = result.vid
    await loadBookshelf()
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

async function clearCookieHandler() {
  try {
    await clearWereadCookie()
    Message.success('Cookie 已清除')
    hasConfig.value = false
    hasTicket.value = false
    connectionStatus.value = 'idle'
    bookshelf.value = []
    bookCount.value = 0
  } catch (e: any) {
    Message.error(e?.message || '清除失败')
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
