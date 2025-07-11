<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
const formRef = ref()
import { useRoute, useRouter } from 'vue-router'
import { getMessageTask, createMessageTask, updateMessageTask } from '@/api/messageTask'
import type { MessageTask, MessageTaskCreate } from '@/types/messageTask'
import cronExpressionPicker from '@/components/cronExpressionPicker.vue'
import MpMultiSelect from '@/components/MpMultiSelect.vue'
import { Message } from '@arco-design/web-vue'
const route = useRoute()
const router = useRouter()
const loading = ref(false)
const isEditMode = ref(false)
const taskId = ref<string | null>(null)
const showCronPicker = ref(false)
const showMpSelector = ref(false)

const cronPickerRef = ref<InstanceType<typeof cronExpressionPicker> | null>(null)
const mpSelectorRef = ref<InstanceType<typeof MpMultiSelect> | null>(null)

const formData = ref<MessageTaskCreate>({
  name: '',
  message_type: 0,
  message_template: '',
  web_hook_url: '',
  mps_id: [],
  status: 1,
  cron_exp: '*/5 * * * *'
})

const fetchTaskDetail = async (id: string) => {
  loading.value = true
  try {
    const res = await getMessageTask(id)
    formData.value = {
      name: res.name,
      message_type: res.message_type,
      message_template: res.message_template,
      web_hook_url: res.web_hook_url,
      mps_id: JSON.parse(res.mps_id||[]),
      status: res.status,
      cron_exp: res.cron_exp
    }
    // 初始化选择器数据
    nextTick(() => {
      if (cronPickerRef.value) {
        cronPickerRef.value.parseExpression(formData.value.cron_exp)
      }
      if (mpSelectorRef.value) {
        mpSelectorRef.value.parseSelected(formData.value.mps_id)
      }
    })
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
  try {
    // 表单验证
  
  loading.value = true
  
  // 表单验证
  try {
    await formRef.value.validate()
  } catch (error) {
    Message.error(error?.errors?.join('\n') || '表单验证失败，请检查输入内容')
    loading.value = false
    return
  }


    loading.value = true
    // 将mps_id转换为字符串
    const submitData = {
      ...formData.value,
      mps_id: JSON.stringify(formData.value.mps_id)
    }
    
    if (isEditMode.value && taskId.value) {
      await updateMessageTask(taskId.value, submitData)
      Message.success('更新任务成功')
    } else {
      await createMessageTask(submitData)
      Message.success('创建任务成功')
    }
    setTimeout(() => {
      router.push('/message-tasks')
    }, 1500)
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
  }
}
const rules = {
  name: [
    { required: true, message: '请输入任务名称' },
    { min: 2, max: 30, message: '公众号名称长度应在2-30个字符之间' }
  ],
  description: [
    { max: 200, message: '描述不能超过200个字符' }
  ]
}
onMounted(() => {
  if (route.params.id) {
    isEditMode.value = true
    taskId.value = route.params.id
    fetchTaskDetail(taskId.value)
  }
})
</script>

<template>
  <a-spin :loading="loading">
    <div class="message-task-form">
      <h2>{{ isEditMode ? '编辑消息任务' : '添加消息任务' }}</h2>
      
      <a-form :model="formData" @submit="handleSubmit" ref="formRef"   :rules="rules">
        <a-form-item label="任务名称" field="name" required>
          <a-input
            v-model="formData.name"
            placeholder="请输入任务名称"
          />
        </a-form-item>
        
        <a-form-item label="类型" field="message_type">
          <a-radio-group v-model="formData.message_type" type="button">
            <a-radio :value="0">Message</a-radio>
            <a-radio :value="1">WebHook</a-radio>
          </a-radio-group>
        </a-form-item>
        
        
        <a-form-item label="消息模板" field="message_template">
          <a-textarea
            v-model="formData.message_template"
            placeholder="请输入消息模板内容"
            :auto-size="{ minRows: 4, maxRows: 8 }"
          />
          <a-button v-if="formData.message_type === 0"
            type="outline" 
            style="margin-top: 8px"
            @click="formData.message_template = '### {{feed.mp_name}} 订阅消息：\n{% if articles %}\n{% for article in articles %}\n- [**{{ article.title }}**]({{article.url}}) ({{ article.publish_time }})\n\n{% endfor %}\n{% else %}\n- 暂无文章\n\n{% endif %}'">
            使用示例消息模板
          </a-button>
          <a-button v-else
            type="outline" 
            style="margin-top: 8px"
            @click="formData.message_template = '{\'articles\': [{% for article in articles %}{{article}}{% if not loop.last %},{% endif %}{% endfor %}]{% endfor %}]}'">
            
            使用示例WebHook模板
          </a-button>
        </a-form-item>

        <a-form-item label="WebHook地址" field="web_hook_url">
          <a-input
            v-model="formData.web_hook_url"
            placeholder="请输入WebHook地址"
          />
          <a-link href="https://open.dingtalk.com/document/orgapp/obtain-the-webhook-address-of-a-custom-robot" target="_blank">如何获取WebHook</a-link>
        </a-form-item>

        <a-form-item label="cron表达式" field="cron_exp" required>
          <a-space>
            <a-input
              v-model="formData.cron_exp"
              placeholder="请输入cron表达式"
              readonly
              style="width: 300px"
            />
            <a-button @click="showCronPicker = true">选择</a-button>
          </a-space>
        </a-form-item>

        <a-form-item label="公众号" field="mps_id">
          <a-space>
            <a-input
              :model-value="(formData.mps_id||[]).map(mp => mp.id.toString()).join(',')"
              placeholder="请选择公众号，留空则对所有公众号生效"
              readonly
              style="width: 300px"
            />
            <a-button @click="showMpSelector = true">选择</a-button>
          </a-space>
        </a-form-item>

        <a-form-item label="状态" field="status">
          <a-radio-group v-model="formData.status" type="button">
            <a-radio :value="1">启用</a-radio>
            <a-radio :value="0">禁用</a-radio>
          </a-radio-group>
        </a-form-item>

        <a-form-item>
          <a-space>
            <a-button html-type="submit" type="primary" :loading="loading">
              提交
            </a-button>
            <a-button @click="router.go(-1)">取消</a-button>
          </a-space>
        </a-form-item>
      </a-form>

      <!-- cron表达式选择器模态框 -->
      <a-modal
        v-model:visible="showCronPicker"
        title="选择cron表达式"
        :footer="false"
        width="800px"
      >
        <cronExpressionPicker 
          ref="cronPickerRef"
          v-model="formData.cron_exp"
        />
        <template #footer>
          <a-button type="primary" @click="showCronPicker = false">确定</a-button>
        </template>
      </a-modal>

      <!-- 公众号选择器模态框 -->
      <a-modal
        v-model:visible="showMpSelector"
        title="选择公众号"
        :footer="false"
        width="800px"
      >
        <MpMultiSelect 
          ref="mpSelectorRef"
          v-model="formData.mps_id"
        />
        <template #footer>
          <a-button type="primary" @click="showMpSelector = false">确定</a-button>
        </template>
      </a-modal>
    </div>
  </a-spin>
</template>

<style scoped>
.message-task-form {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

h2 {
  margin-bottom: 20px;
  color: var(--color-text-1);
}
</style>