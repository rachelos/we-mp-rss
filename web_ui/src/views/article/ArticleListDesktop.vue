<template>
  <a-spin :loading="fullLoading" tip="正在刷新..." size="large">
    <a-layout class="article-list">
      <a-layout-sider :width="300"
        :style="{ background: '#fff', padding: '0', borderRight: '1px solid #eee', display: 'flex', flexDirection: 'column', border: 0 }">
        <a-card :bordered="false" title="公众号"
          :headStyle="{ padding: '12px 16px', borderBottom: '1px solid #eee', background: '#fff', zIndex: 1, border: 0 }">
          <template #extra>
            <a-dropdown>
              <a-button type="primary">
                <template #icon><icon-plus /></template>
                订阅
                <icon-down />
              </a-button>
              <template #content>
                <a-doption @click="showAddModal"><template #icon><icon-plus /></template>添加公众号</a-doption>
                <a-doption @click="exportMPS"><template #icon><icon-export /></template>导出公众号</a-doption>
                <a-doption @click="importMPS"><template #icon><icon-import /></template>导入公众号</a-doption>
                <a-doption @click="exportOPML"><template #icon><icon-share-external /></template>导出OPML</a-doption>
              </template>
            </a-dropdown>
          </template>
          <div style="display: flex; flex-direction: column;; background: #fff">
            <a-list :data="mpList" :loading="mpLoading" bordered>
              <template #item="{ item, index }">
                <a-list-item @click="handleMpClick(item.id)" :class="{ 'active-mp': activeMpId === item.id }"
                  style="padding: 9px 8px; cursor: pointer; display: flex; align-items: center; justify-content: space-between;">
                  <div style="display: flex; align-items: center;">
                    <img :src="Avatar(item.avatar)" width="40" style="float:left;margin-right:1rem;" />
                    <a-typography-text strong style="line-height:32px;">
                      {{ item.name || item.mp_name }}
                    </a-typography-text>
                    <a-button v-if="activeMpId === item.id && item.id != ''" size="mini" type="text" status="danger"
                      @click="$event.stopPropagation(); deleteMp(item.id)">
                      <template #icon><icon-delete /></template>
                    </a-button>
                  </div>
                </a-list-item>
              </template>
            </a-list>
            <a-pagination :total="mpPagination.total" simple @change="handleMpPageChange" :show-total="true"
              style="margin-top: 1rem;" />
          </div>
        </a-card>
      </a-layout-sider>

      <a-layout-content :style="{ padding: '20px', width: '100%' }">
        <a-page-header :title="activeFeed ? activeFeed.name : '全部'" :subtitle="'管理您的公众号订阅内容'" :show-back="false">
          <template #extra>
            <a-space>
              <a-button @click="refresh" v-if="activeFeed?.id != ''">
                <template #icon><icon-refresh /></template>
                刷新
              </a-button>
              <a-button @click="clear_articles" v-else>
                <template #icon><icon-delete /></template>
                清理无效文章
              </a-button>
              <a-button @click="clear_duplicate_article" v-if="activeFeed?.id == ''">
                <template #icon><icon-delete /></template>
                清理重复文章
              </a-button>
              <a-button @click="handleAuthClick">
                <template #icon><icon-scan /></template>
                刷新授权
              </a-button>
              <a-dropdown>
                <a-button>
                  <template #icon>
                    <IconWifi />
                  </template>
                  订阅
                  <icon-down />
                </a-button>
                <template #content>
                  <a-doption @click="rssFormat = 'atom'; openRssFeed()"><template #icon>
                      <TextIcon text="atom" />
                    </template>ATOM</a-doption>
                  <a-doption @click="rssFormat = 'rss'; openRssFeed()"><template #icon>
                      <TextIcon text="rss" />
                    </template>RSS</a-doption>
                  <a-doption @click="rssFormat = 'json'; openRssFeed()"><template #icon>
                      <TextIcon text="json" />
                    </template>JSON</a-doption>
                  <a-doption @click="rssFormat = 'md'; openRssFeed()"><template #icon>
                      <TextIcon text="md" />
                    </template>Markdown</a-doption>
                  <a-doption @click="rssFormat = 'txt'; openRssFeed()"><template #icon>
                      <TextIcon text="txt" />
                    </template>Text</a-doption>
                </template>
              </a-dropdown>
              <a-button type="primary" status="danger" @click="handleBatchDelete" :disabled="!selectedRowKeys.length">
                <template #icon><icon-delete /></template>
                批量删除
              </a-button>
            </a-space>
          </template>
        </a-page-header>

        <a-card style="border:0">
          <a-alert type="success" closable>{{ activeFeed?.mp_intro || "请选择一个公众号码进行管理,搜索文章后再点击订阅会有惊喜哟！！！" }}</a-alert>
          <div class="search-bar">
            <a-input-search v-model="searchText" placeholder="搜索文章标题" @search="handleSearch" @keyup.enter="handleSearch"
              allow-clear />
          </div>

          <a-table :columns="columns" :data="articles" :loading="loading" :pagination="pagination" :row-selection="{
            type: 'checkbox',
            showCheckedAll: true,
            width: 50,
            fixed: true,
            checkStrictly: true,
            onlyCurrent: false
          }" row-key="id" @page-change="handlePageChange" v-model:selectedKeys="selectedRowKeys">
            <template #status="{ record }">
              <a-tag :color="statusColorMap[record.status]">
                {{ statusTextMap[record.status] }}
              </a-tag>
            </template>
            <template #actions="{ record }">
              <a-space>
                <a-button type="text" @click="viewArticle(record)" :title="record.id">
                  <template #icon><icon-eye /></template>
                </a-button>
                <a-button type="text" status="danger" @click="deleteArticle(record.id)">
                  <template #icon><icon-delete /></template>
                </a-button>
              </a-space>
            </template>
          </a-table>


          <a-modal v-model:visible="refreshModalVisible" title="刷新设置">
            <a-form :model="refreshForm" :rules="refreshRules">
              <a-form-item label="起始页" field="startPage">
                <a-input-number v-model="refreshForm.startPage" :min="1" />
              </a-form-item>
              <a-form-item label="结束页" field="endPage">
                <a-input-number v-model="refreshForm.endPage" :min="1" />
              </a-form-item>
            </a-form>
            <template #footer>
              <a-button @click="refreshModalVisible = false">取消</a-button>
              <a-button type="primary" @click="handleRefresh">确定</a-button>
            </template>
          </a-modal>
          <a-modal id="article-model" v-model:visible="articleModalVisible" 
            placement="left" :footer="false" :fullscreen="false" @before-close="resetScrollPosition">
            <h2 id="topreader">{{ currentArticle.title }}</h2>
            <div style="margin-top: 20px; color: var(--color-text-3); text-align: left">
              <a-link :href="currentArticle.url" target="_blank">查看原文</a-link>
              更新时间 ：{{ currentArticle.time }}
            <a-link @click="viewArticle(currentArticle,-1)" target="_blank">上一篇 </a-link>
            <a-space/>
            <a-link @click="viewArticle(currentArticle,1)" target="_blank">下一篇 </a-link>
            </div>
            <div v-html="currentArticle.content"></div>

            <div style="margin-top: 20px; color: var(--color-text-3); text-align: right">
              {{ currentArticle.time }}
            </div>
          </a-modal>
        </a-card>
      </a-layout-content>
    </a-layout>
  </a-spin>
</template>

<script setup lang="ts">
import { Avatar } from '@/utils/constants'
import { translatePage, setCurrentLanguage } from '@/utils/translate';
import { ref, onMounted, h } from 'vue'
import axios from 'axios'
import { IconApps, IconAtt, IconDelete, IconEdit, IconEye, IconRefresh, IconScan, IconWeiboCircleFill, IconWifi, IconCode } from '@arco-design/web-vue/es/icon'
import { getArticles, deleteArticle as deleteArticleApi, ClearArticle, ClearDuplicateArticle, getArticleDetail } from '@/api/article'
import { ExportOPML, ExportMPS, ImportMPS } from '@/api/export'
import { getSubscriptions, UpdateMps } from '@/api/subscription'
import { inject } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { formatDateTime, formatTimestamp } from '@/utils/date'
import router from '@/router'
import { deleteMpApi } from '@/api/subscription'
import TextIcon from '@/components/TextIcon.vue'

const articles = ref([])
const loading = ref(false)
const mpList = ref([])
const mpLoading = ref(false)
const activeMpId = ref('')
const selectedRowKeys = ref([])
const mpPagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
  showPageSize: false,
  showJumper: false,
  showTotal: true,
  pageSizeOptions: [5, 10, 15]
})
const searchText = ref('')
const filterStatus = ref('')

const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
  showTotal: true,
  showJumper: true,
  showPageSize: true,
  pageSizeOptions: [10]
})

const statusTextMap = {
  published: '已发布',
  draft: '草稿',
  deleted: '已删除'
}

const statusColorMap = {
  published: 'green',
  draft: 'orange',
  deleted: 'red'
}

const columns = [
  {
    title: '文章标题',
    dataIndex: 'title',
    width: window.innerWidth - 1000,
    ellipsis: true,
    render: ({ record }) => h('a', {
      href: record.url || '#',
      title: record.title,
      target: '_blank',
      style: { color: 'var(--color-text-1)' }
    }, record.title)
  },
  {
    title: '公众号',
    dataIndex: 'mp_id',
    width: '120',
    ellipsis: true,
    render: ({ record }) => {
      const mp = mpList.value.find(item => item.id === record.mp_id);
      return h('span', {
        style: { color: 'var(--color-text-3)' }
      }, record.mp_name || mp?.name || record.mp_id)
    }
  },
  {
    title: '更新时间',
    dataIndex: 'created_at',
    width: '140',
    render: ({ record }) => h('span',
      { style: { color: 'var(--color-text-3)', fontSize: '12px' } },
      formatDateTime(record.created_at)
    )
  },
  {
    title: '发布时间',
    dataIndex: 'publish_time',
    width: '140',
    render: ({ record }) => h('span',
      { style: { color: 'var(--color-text-3)', fontSize: '12px' } },
      formatTimestamp(record.publish_time)
    )
  },
  {
    title: '操作',
    dataIndex: 'actions',
    slotName: 'actions'
  }
]

const handleMpPageChange = (page: number, pageSize: number) => {
  mpPagination.value.current = page
  mpPagination.value.pageSize = pageSize
  fetchMpList()
}
const rssFormat = ref('atom')
const activeFeed = ref({
  id: "",
  name: "全部",
})
const handleMpClick = (mpId: string) => {
  activeMpId.value = mpId
  pagination.value.current = 1
  activeFeed.value = mpList.value.find(item => item.id === activeMpId.value)
  console.log(activeFeed.value)

  fetchArticles()
}

const fetchArticles = async () => {
  loading.value = true
  try {
    console.log('请求参数:', {
      page: pagination.value.current - 1,
      pageSize: pagination.value.pageSize,
      search: searchText.value,
      status: filterStatus.value,
      mp_id: activeMpId.value
    })

    const res = await getArticles({
      page: pagination.value.current - 1,
      pageSize: pagination.value.pageSize,
      search: searchText.value,
      status: filterStatus.value,
      mp_id: activeMpId.value
    })

    // 确保数据包含必要字段
    articles.value = (res.list || []).map(item => ({
      ...item,
      mp_name: item.mp_name || item.account_name || '未知公众号',
      publish_time: item.publish_time || item.create_time || '-',
      url: item.url || "https://mp.weixin.qq.com/s/" + item.id
    }))
    pagination.value.total = res.total || 0
  } catch (error) {
    console.error('获取文章列表错误:', error)
    Message.error(error)
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number, pageSize: number, type?: string) => {
  console.log('分页事件触发:', { page, pageSize, type })
  pagination.value.current = page
  pagination.value.pageSize = pageSize
  fetchArticles()
}

const handleSearch = () => {
  pagination.value.current = 1
  fetchArticles()
}

const wechatAuthQrcodeRef = ref()
const showAuthQrcode = inject('showAuthQrcode') as () => void
const handleAuthClick = () => {
  showAuthQrcode()
}

const exportOPML = async () => {
  try {
    const response = await ExportOPML();
    const blob = new Blob([response], { type: 'application/xml' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'rss_feed.opml';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (error) {
    console.error('导出OPML失败:', error);
    Message.error(error?.message || '导出OPML失败');
  }
};
const exportMPS = async () => {
  try {
    const res = await ExportMPS();
    const data = (res as any).data ?? res;
    const blob = data instanceof Blob
      ? data
      : new Blob([data], { type: 'text/csv;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '公众号列表.csv';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (error: any) {
    Message.error(error?.message || '导出公众号失败');
  }
};

const importMPS = async () => {
  try {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv';
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      const res = await ImportMPS(formData);
      const data = (res as any).data ?? res;
      Message.info(data?.message || "导入成功");
      // 自动刷新
      await Promise.all([fetchMpList(), fetchArticles()]);
    };
    input.click();
  } catch (error: any) {
    Message.error(error?.message || '导入公众号失败');
  }
};

const openRssFeed = () => {
  const format = ['rss', 'atom', 'json', 'md', 'txt'].includes(rssFormat.value)
    ? rssFormat.value
    : 'atom'
  let search = ""
  if (searchText.value != "") {
    search = "/search/" + searchText.value;
  }
  if (!activeMpId.value) {
    window.open(`/feed${search}/all.${format}`, '_blank')
    return
  }
  const activeMp = mpList.value.find(item => item.id === activeMpId.value)
  if (activeMp) {
    window.open(`/feed${search}/${activeMpId.value}.${format}`, '_blank')
  }
}

const resetScrollPosition = () => {
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  });
}

const fullLoading = ref(false)

const refreshModalVisible = ref(false)
const refreshForm = ref({
  startPage: 0,
  endPage: 1
})
const refreshRules = {
  startPage: [{ required: true, message: '请输入开始页码' }],
  endPage: [{ required: true, message: '请输入结束页码' }]
}

const showRefreshModal = () => {
  refreshModalVisible.value = true
}

const handleRefresh = () => {
  fullLoading.value = true
  UpdateMps(activeMpId.value, {
    start_page: refreshForm.value.startPage,
    end_page: refreshForm.value.endPage
  }).then(() => {
    Message.success('刷新成功')
    refreshModalVisible.value = false
  }).finally(() => {
    fullLoading.value = false
  })
  fetchArticles()
}
const clear_articles = () => {
  fullLoading.value = true
  ClearArticle().then((res) => {
    Message.success(res?.message || '清理成功')
    refreshModalVisible.value = false
  }).finally(() => {
    fullLoading.value = false
  })
  fetchArticles()
}
const clear_duplicate_article = () => {
  fullLoading.value = true
  ClearDuplicateArticle().then((res) => {
    Message.success(res?.message || '清理成功')
    refreshModalVisible.value = false
  }).finally(() => {
    fullLoading.value = false
  })
  fetchArticles()
}

const refresh = () => {
  showRefreshModal()
}

const showAddModal = () => {
  router.push('/add-subscription')
}

const handleAddSuccess = () => {
  fetchArticles()
}
 const processedContent = (record: any) => {
 return record.content.replace(
      /(<img[^>]*src=["'])(?!\/static\/res\/logo\/)([^"']*)/g,
      '$1/static/res/logo/$2'
 ).replace(/<img([^>]*)width=["'][^"']*["']([^>]*)>/g, '<img$1$2>')
 }
const viewArticle = async (record: any,action_type: number) => {
  loading.value = true
  try {
    // console.log(record)
    const article = await getArticleDetail(record.id,action_type)
    currentArticle.value = {
      id: article.id,
      title: article.title,
      content: processedContent(article),
      time: formatDateTime(article.created_at),
      url: article.url
    }
    articleModalVisible.value = true
    window.location="#topreader"
  } catch (error) {
    console.error('获取文章详情错误:', error)
    Message.error(error)
  } finally {
    loading.value = false
  }
}
const currentArticle = ref({
  title: '',
  content: '',
  time: '',
  url: ''
})
const articleModalVisible = ref(false)

const deleteArticle = (id: number) => {
  Modal.confirm({
    title: '确认删除',
    content: '确定要删除该文章吗？删除后将无法恢复。',
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      await deleteArticleApi(id);
      Message.success('删除成功');
      fetchArticles();
    },
    onCancel: () => {
      Message.info('已取消删除操作');
    }
  });
}

const handleBatchDelete = () => {
  Modal.confirm({
    title: '确认批量删除',
    content: `确定要删除选中的${selectedRowKeys.value.length}篇文章吗？删除后将无法恢复。`,
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        await Promise.all(selectedRowKeys.value.map(id => deleteArticleApi(id)));
        Message.success(`成功删除${selectedRowKeys.value.length}篇文章`);
        selectedRowKeys.value = [];
        fetchArticles();
      } catch (error) {
        Message.error('删除部分文章失败');
      }
    },
    onCancel: () => {
      Message.info('已取消批量删除操作');
    }
  });
}

onMounted(() => {
  console.log('组件挂载，开始获取数据')
  fetchMpList().then(() => {
    console.log('公众号列表获取完成')
    fetchArticles()
  }).catch(err => {
    console.error('初始化失败:', err)
  })
})

const fetchMpList = async () => {
  mpLoading.value = true
  try {
    const res = await getSubscriptions({
      page: mpPagination.value.current - 1,
      pageSize: mpPagination.value.pageSize
    })

    mpList.value = res.list.map(item => ({
      id: item.id || item.mp_id,
      name: item.name || item.mp_name,
      avatar: item.avatar || item.mp_cover || '',
      mp_intro: item.mp_intro || item.mp_intro || '',
      article_count: item.article_count || 0
    }))
    // 添加'全部'选项
    mpList.value.unshift({
      id: '',
      name: '全部',
      avatar: '/static/logo.svg',
      mp_intro: '显示所有公众号文章',
      article_count: res.total || 0
    });
    mpPagination.value.total = res.total || 0
  } catch (error) {
    console.error('获取公众号列表错误:', error)
  } finally {
    mpLoading.value = false
  }
}
const deleteMp = async (mpId: string) => {
  try {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除该订阅号吗？删除后将无法恢复。',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        await deleteMpApi(mpId);
        Message.success('订阅号删除成功');
        fetchMpList();
      },
      onCancel: () => {
        Message.info('已取消删除操作');
      }
    });
  } catch (error) {
    console.error('删除订阅号失败:', error);
    Message.error('删除订阅号失败，请稍后重试');
  }
}

const importArticles = () => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;

    try {
      const content = await file.text();
      const data = JSON.parse(content);
      // 这里应该调用API导入数据
      Message.success(`成功导入${data.length}篇文章`);
    } catch (error) {
      console.error('导入文章失败:', error);
      Message.error('导入失败，请检查文件格式');
    }
  };
  input.click();
};

const exportArticles = () => {
  if (!articles.value.length) {
    Message.warning('没有文章可导出');
    return;
  }

  const data = JSON.stringify(articles.value, null, 2);
  const blob = new Blob([data], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `articles_${activeMpId.value || 'all'}_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  Message.success('导出成功');
};
</script>

<style scoped>
.article-list {
  /* height: calc(100vh - 186px); */
}

.a-layout-sider {
  overflow: hidden;
}

.a-list-item {
  cursor: pointer;
  padding: 12px 16px;
  transition: all 0.2s;
  margin-bottom: 0 !important;
}

.a-list-item:hover {
  background-color: var(--color-fill-2);
}

.active-mp {
  background-color: var(--color-primary-light-1);
}

.search-bar {
  display: flex;
  margin-bottom: 20px;
}

.arco-drawer-body img {
  max-width: 100vw !important;
  margin: 0 auto !important;
  padding: 0 !important;
}

.arco-drawer-body {
  z-index: 9999 !important;
  /* 确保抽屉在其他内容之上 */
}

:deep(.arco-btn .arco-icon-down) {
  transition: transform 0.2s ease-in-out;
}

:deep(.arco-dropdown-open .arco-icon-down) {
  transform: rotate(180deg);
}

</style>
<style>
#article-model img {
  max-width: 100% !important;
  border-width:0px !important;
}
iframe{
  width:100% !important;
  border:0 !important;
}
</style>