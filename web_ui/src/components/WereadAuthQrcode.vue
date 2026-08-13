<template>
  <a-modal
    v-model:visible="visible"
    title="微信读书扫码授权"
    :footer="false"
    :mask-closable="false"
    width="420px"
    @cancel="handleCancel"
  >
    <div class="weread-qrcode-container">
      <!-- 加载中 -->
      <div v-if="loading" class="loading">
        <a-spin size="large" />
        <p>正在获取二维码...</p>
      </div>

      <!-- 二维码展示 -->
      <div v-else-if="qrcodeUrl" class="qrcode-section">
        <div class="qrcode-img-wrapper">
          <img :src="qrcodeUrl" alt="微信读书授权二维码" />
          <div v-if="qrExpired" class="qrcode-expired-mask">
            <div class="expired-content">
              <icon-exclamation-circle-fill />
              <p>二维码已过期</p>
              <a-button type="primary" size="small" @click="refreshQrCode">刷新二维码</a-button>
            </div>
          </div>
        </div>
        <p class="qrcode-tip">请使用微信扫描二维码授权</p>
        <p class="qrcode-desc">用微信「扫一扫」扫码，确认登录微信读书网页版</p>

        <!-- 等待状态 -->
        <div v-if="statusMsg && !loginSuccess" class="status-indicator">
          <a-tag color="arcoblue">
            <template #icon><icon-loading /></template>
            {{ statusMsg }}
          </a-tag>
        </div>

        <!-- 登录成功 -->
        <div v-if="loginSuccess" class="success-indicator">
          <a-alert type="success">
            <template #icon><icon-check-circle-fill /></template>
            授权成功！用户 ID: {{ loginVid }}
          </a-alert>
        </div>
      </div>

      <!-- 错误状态 -->
      <div v-else class="error-section">
        <a-alert type="error" :title="errorMessage" />
        <a-button type="primary" @click="startAuth" style="margin-top: 16px">
          <template #icon><icon-refresh /></template>
          重试
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<script lang="ts" setup>
import { ref, onUnmounted } from 'vue'
import {
  getWereadQrCode,
  checkWereadQrStatus,
  completeWereadQrLogin,
} from '@/api/weread'
import { Message } from '@arco-design/web-vue'

const emit = defineEmits(['success', 'cancel'])

const visible = ref(false)
const loading = ref(false)
const qrcodeUrl = ref('')
const qrExpired = ref(false)
const errorMessage = ref('')
const statusMsg = ref('')
const loginSuccess = ref(false)
const loginVid = ref('')

let pollTimer: number | null = null
let uid: string = ''

// 启动授权流程
const startAuth = async () => {
  try {
    visible.value = true
    loading.value = true
    errorMessage.value = ''
    statusMsg.value = ''
    qrExpired.value = false
    loginSuccess.value = false
    loginVid.value = ''

    const res = await getWereadQrCode() as any
    const codeUrl = res?.code

    if (!codeUrl) {
      loading.value = false
      errorMessage.value = '获取二维码失败'
      return
    }

    qrcodeUrl.value = codeUrl
    uid = res?.uid || ''
    loading.value = false

    // 开始轮询
    statusMsg.value = '等待扫码...'
    startPolling()
  } catch (err: any) {
    loading.value = false
    errorMessage.value = typeof err === 'string' ? err : (err?.message || '获取二维码失败')
    emit('cancel', err)
  }
}

// 轮询扫码状态
const startPolling = () => {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      const res = await checkWereadQrStatus() as any

      if (res?.login_status) {
        // 登录成功
        stopPolling()
        loginSuccess.value = true
        loginVid.value = res?.data?.vid || ''
        statusMsg.value = ''

        // 完成登录流程
        await completeWereadQrLogin()

        Message.success('微信读书授权成功')

        // 延迟关闭弹窗，让用户看到成功提示
        setTimeout(() => {
          visible.value = false
          emit('success', {
            vid: loginVid.value,
            cookies: res?.data?.cookies || {},
          })
        }, 1500)

        return
      }

      // 更新状态消息
      const msg = res?.msg || ''
      if (msg.includes('过期') || msg.includes('超时')) {
        qrExpired.value = true
        stopPolling()
        return
      }

      // 根据 logicCode 显示不同提示
      const logicCode = res?.data?.logicCode
      if (logicCode === 1) {
        statusMsg.value = '已扫码，请在手机上确认登录...'
      } else if (logicCode === 'NEED_OTP') {
        statusMsg.value = '需要短信验证码，当前暂不支持'
        stopPolling()
      } else if (logicCode === 'LOGIN_TIMEOUT') {
        qrExpired.value = true
        stopPolling()
      } else {
        statusMsg.value = '等待扫码...'
      }
    } catch (err: any) {
      // 轮询出错不中断，继续重试
      console.warn('轮询微信读书二维码状态失败:', err)
    }
  }, 2000)
}

// 停止轮询
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 刷新二维码
const refreshQrCode = async () => {
  qrExpired.value = false
  loading.value = true
  try {
    const res = await getWereadQrCode() as any
    const codeUrl = res?.code
    if (codeUrl) {
      qrcodeUrl.value = codeUrl
      uid = res?.uid || ''
      statusMsg.value = '等待扫码...'
      startPolling()
    } else {
      errorMessage.value = '刷新二维码失败'
    }
  } catch (err) {
    errorMessage.value = '刷新二维码失败'
  } finally {
    loading.value = false
  }
}

// 取消/关闭弹窗
const handleCancel = () => {
  stopPolling()
  if (!loginSuccess.value) {
    emit('cancel')
  }
}

// 组件卸载时清理
onUnmounted(() => {
  stopPolling()
})

defineExpose({
  startAuth,
  close: handleCancel,
})
</script>

<style scoped>
.weread-qrcode-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 8px;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 0;
}

.qrcode-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.qrcode-img-wrapper {
  position: relative;
  width: 220px;
  height: 220px;
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.qrcode-img-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.qrcode-expired-mask {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.92);
  display: flex;
  align-items: center;
  justify-content: center;
}

.expired-content {
  text-align: center;
  color: var(--color-text-2);
  font-size: 14px;
}

.expired-content p {
  margin: 8px 0;
}

.qrcode-tip {
  font-size: 15px;
  font-weight: 500;
  color: var(--color-text-1);
  margin: 0;
}

.qrcode-desc {
  font-size: 12px;
  color: var(--color-text-3);
  margin: 0;
}

.status-indicator {
  margin-top: 4px;
}

.success-indicator {
  width: 100%;
  margin-top: 8px;
}

.error-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 0;
}
</style>
