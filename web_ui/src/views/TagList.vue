<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ExportTags, ImportTags } from '@/api/export'
import { listTags, deleteTag } from '@/api/tagManagement'
import type { Tag } from '@/types/tagManagement'
import { Message, Modal } from '@arco-design/web-vue'
import { IconExport, IconImport } from '@arco-design/web-vue/es/icon'

const loading = ref(false)
const loadingMore = ref(false)
const tags = ref<Tag[]>([])
const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0
})
const isMobile = ref(window.innerWidth < 768)
const handleResize = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
})

const fetchTags = async (isLoadMore = false) => {
  try {
    if (isLoadMore) {
      loadingMore.value = true
    } else {
      loading.value = true
    }
    const res = await listTags({
      offset: (pagination.value.current - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize
    })
    console.log(res)
    if (isLoadMore) {
      tags.value = [...tags.value, ...(res.list || [])]
    } else {
      tags.value = res.list || []
    }
    pagination.value.total = res.total || 0
  } catch (error) {
    Message.error('获取标签列表失败')
  } finally {
    if (isLoadMore) {
      loadingMore.value = false
    } else {
      loading.value = false
    }
  }
}

const handleDelete = async (id: string) => {
  try {
    await deleteTag(id)
    Message.success('删除成功')
    fetchTags()
  } catch (error) {
    Message.error('删除失败')
  }
}

const exportTags = async () => {
  Message.info('正在生成导出文件，请稍候...');
  try {
    const res = await ExportTags();
    const data = (res as any).data ?? res;
    const blob = data instanceof Blob
      ? data
      : new Blob([data], { type: 'text/csv;charset=utf-8' });

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '标签列表.csv'; // 指定下载文件名
    document.body.appendChild(a);
    a.click();

    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    Message.success('文件导出成功！');
  } catch (error: any) {
    console.error('导出标签失败:', error);
    const errorMessage = error?.message || '导出标签失败，请检查网络或联系管理员';
    Message.error(errorMessage);
  }
};

const importTags = async () => {
  try {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv';

    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;

      const formData = new FormData();
      formData.append('file', file);

      Message.info('正在导入文件，请稍候...');
      try {
        const res = await ImportTags(formData);
        const data = (res as any).data ?? res;
        Message.success(data?.message || "导入成功");
        // 导入成功后，刷新列表
        fetchTags();
      } catch (importError: any) {
        const detail = importError.response?.data?.detail;
        const errorMessage = (typeof detail === 'object' && detail.message) ? detail.message : (detail || '导入失败，请检查文件格式或联系管理员');
        Message.error(errorMessage);
        console.error('导入标签时发生错误:', importError);
      }
    };

    input.click();
  } catch (error: any) {
    Message.error(error?.message || '无法打开文件选择器');
  }
};


const handlePageChange = (page: number) => {
  pagination.value.current = page
  fetchTags()
}

onMounted(() => {
  fetchTags()
})
</script>

<template>
  <div class="tag-list">
    <a-page-header title="标签管理" subtitle="管理文章标签">
      <template #extra>
        <a-space>
          <a-button @click="exportTags">
            <template #icon><icon-export /></template>
            导出标签
          </a-button>

          <a-button @click="importTags">
            <template #icon><icon-import /></template>
            导入标签
          </a-button>

          <a-button type="primary" @click="$router.push('/tags/add')">
          <template #icon><icon-plus /></template>
            添加标签
          </a-button>
        </a-space>
      </template>
    </a-page-header>

    <a-card>
      <a-table
        v-if="!isMobile"
        :loading="loading"
        :data="tags"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #columns>
          <a-table-column title="标签名称" data-index="name" />
          <a-table-column title="状态" data-index="status">
            <template #cell="{ record }">
              <a-tag v-if="record.status === 1" color="green">启用</a-tag>
              <a-tag v-else color="red">禁用</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="创建时间" data-index="created_at" />
          <a-table-column title="操作">
            <template #cell="{ record }">
              <a-space>
                <a-button type="text" :href="`/feed/tag/${record.id}.rss`" target="_blank">
                  订阅
                </a-button>
                <a-button type="text" @click="$router.push(`/tags/edit/${record.id}`)">
                  编辑
                </a-button>
                <a-popconfirm content="确认删除该标签？" @ok="handleDelete(record.id)">
                  <a-button type="text" status="danger">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>

      <a-list
        v-else
        :loading="loading"
        :loading-more="loadingMore"
        :data="tags"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #item="{ item }">
          <a-list-item>
            <a-list-item-meta>
              <template #title>
                {{ item.name }}
                <a-tag v-if="item.status === 1" color="green" size="small">启用</a-tag>
                <a-tag v-else color="red" size="small">禁用</a-tag>
              </template>
              <template #description>
                创建时间: {{ item.created_at }}
              </template>
            </a-list-item-meta>
            <a-space>
              <a-button type="text" size="small" :href="`/feed/tag/${item.id}.rss`" target="_blank">
                订阅
              </a-button>
              <a-button type="text" size="small" @click="$router.push(`/tags/edit/${item.id}`)">
                编辑
              </a-button>
              <a-popconfirm content="确认删除该标签？" @ok="handleDelete(item.id)">
                <a-button type="text" status="danger" size="small">删除</a-button>
              </a-popconfirm>
            </a-space>
          </a-list-item>
        </template>
      <template #footer>
          <div v-if="pagination.current * pagination.pageSize < pagination.total" class="load-more">
            <a-button
              type="primary"
              :loading="loadingMore"
              @click="() => {
                pagination.current++
                fetchTags(true)
              }"
            >
              加载更多
            </a-button>
              <div class="total-count">
                共 {{ pagination.total }} 条
              </div>
            </div>
        </template>
      </a-list>
    </a-card>
  </div>
</template>

<style scoped>
.tag-list {
  padding: 16px;
}
.load-more{
    width: 120px;
    margin: 0px auto;
    text-align: center;
}
</style>