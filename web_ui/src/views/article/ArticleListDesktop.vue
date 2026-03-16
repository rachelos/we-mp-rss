<template>
  <a-spin class="article-list-spin" :style="{ display: 'block', width: '100%' }" :loading="fullLoading" tip="正在刷新..." size="large">
    <a-layout class="article-list">
      
      <a-layout-sider
        :width="siderCollapsed ? 0 : 300"
        :style="{
          background: '#fff',
          padding: '0',
          borderRight: siderCollapsed ? '0' : '1px solid #eee',
          display: 'flex',
          flexDirection: 'column',
          border: 0,
          overflow: 'hidden',
          transition: 'width 0.2s ease'
        }"
      >
        <div v-show="!siderCollapsed" style="height: 100%;">
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
                <a-doption @click="showAddFeaturedArticleModal"><template #icon><icon-link /></template>添加精选文章</a-doption>
                <a-doption @click="exportMPS"><template #icon><icon-export /></template>导出公众号</a-doption>
                <a-doption @click="importMPS"><template #icon><icon-import /></template>导入公众号</a-doption>
                <a-doption @click="exportOPML"><template #icon><icon-share-external /></template>导出OPML</a-doption>
              </template>
            </a-dropdown>
          </template>
          <div style="display: flex; flex-direction: column;; background: #fff">
            <div style="margin-bottom: 12px;">
              <a-input-search 
                v-model="mpSearchText" 
                placeholder="搜索公众号名称" 
                @search="handleMpSearch" 
                @keyup.enter="handleMpSearch"
                allow-clear 
                size="small" />
            </div>
            <div style="margin-bottom: 8px; padding: 0 8px;">
              <a-radio-group v-model="mpFilterType" type="button" size="small" style="width: 100%;">
                <a-radio value="active" style="flex: 1; text-align: center;">启用</a-radio>
                <a-radio value="disabled" style="flex: 1; text-align: center;">停用</a-radio>
                <a-radio value="all" style="flex: 1; text-align: center;">全部</a-radio>
              </a-radio-group>
            </div>
            <a-list :data="filteredMpList" :loading="mpLoading" bordered>
              <template #item="{ item, index }">
                <a-list-item @click="handleMpClick(item.id)" :class="{ 'active-mp': activeMpId === item.id }"
                  style="padding: 9px 8px; cursor: pointer; display: flex; align-items: center; justify-content: space-between;">
                  <div style="display: flex; align-items: center;">
                    <img :src="Avatar(item.avatar)" width="40" style="float:left;margin-right:1rem;" />
                    <a-typography-text strong style="line-height:32px;" :style="{ opacity: item.status === 0 ? 0.5 : 1 }">
                      {{ item.name || item.mp_name }}
                    </a-typography-text>
                    <a-button v-if="activeMpId === item.id && canManageMp(item.id)" size="mini" type="text" status="danger"
                      @click="$event.stopPropagation(); deleteMp(item.id)">
                      <template #icon><icon-delete /></template>
                    </a-button>
                    <a-button v-if="activeMpId === item.id && canManageMp(item.id)" size="mini" type="text"
                      @click="$event.stopPropagation(); copyMpId(item.id)">
                      <template #icon><icon-copy /></template>
                    </a-button>
                    <a-button v-if="activeMpId === item.id && canManageMp(item.id)" size="mini" type="text"
                      @click="$event.stopPropagation(); toggleMpStatus(item.id, item.status === 1 ? 0 : 1)">
                      <template #icon>
                        <icon-stop v-if="item.status === 1" />
                        <icon-play-arrow v-else />
                      </template>
                    </a-button>
                  </div>
                </a-list-item>
              </template>
            </a-list>
            <a-pagination :total="mpPagination.total" simple @change="handleMpPageChange" :show-total="true"
              style="margin-top: 1rem;" />
          </div>
          </a-card>
        </div>
      </a-layout-sider>

      <a-layout-content :style="{ padding: '20px', paddingLeft: siderCollapsed ? '8px' : '20px', minWidth: '0', flex: '1 1 0' }">
        <a-page-header :subtitle="'管理您的公众号订阅内容'" :show-back="false">
          <template #title>
            <a-space>
              <a-button
                type="text"
                size="small"
                @click="siderCollapsed = !siderCollapsed"
                :title="siderCollapsed ? '展开侧栏' : '折叠侧栏'"
                :aria-label="siderCollapsed ? '展开侧栏' : '折叠侧栏'"
              >
                <template #icon>
                  <IconMenuUnfold v-if="siderCollapsed" />
                  <IconMenuFold v-else />
                </template>
              </a-button>
              <span>{{ activeFeed ? activeFeed.name : '全部' }}</span>
            </a-space>
          </template>
          <template #extra>
            <a-space>
              <span style="font-size: 12px; color: var(--color-text-3);">{{ issourceUrl ? '原链接' : '内链' }}</span>
              <a-switch 
                v-model="issourceUrl" 
                size="small" 
                style="margin: 0 8px;">
              </a-switch>

              <a-button  @click="handleExportShow()">
                <template #icon><icon-export /></template>
                导出
              </a-button>
              <ExportModal ref="exportModal"  />
              <a-button @click="refresh" v-if="activeFeed?.id != '' && activeFeed?.id !== FEATURED_MP_ID">
                <template #icon><icon-refresh /></template>
                刷新
              </a-button>
              <a-dropdown>
                <a-button v-if="activeFeed?.id == ''">
                  <template #icon><icon-delete /></template>
                  清理
                  <icon-down />
                </a-button>
                <template #content>
                  <a-doption @click="clear_articles">
                    <template #icon> <TextIcon text="E" /></template>
                    清理无效文章
                  </a-doption>
                  <a-doption @click="clear_duplicate_article">
                    <template #icon> <TextIcon text="C" /></template>
                    清理重复文章
                  </a-doption>
                </template>
              </a-dropdown>
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
             <a-input-search class="search-input" v-model="searchText" placeholder="搜索文章标题" @search="handleSearch" @keyup.enter="handleSearch"
               allow-clear />
             <a-checkbox class="favorite-filter" :model-value="onlyFavorite" @change="handleFavoriteFilterChange">仅显示已收藏</a-checkbox>
           </div>
          <div class="article-table-scroll">
            <a-table :columns="columns" :data="articles" :loading="loading" :pagination="pagination" :scroll="{ x: 1500 }" :row-selection="{
              type: 'checkbox',
              showCheckedAll: true,
              width: 50,
              fixed: true,
              checkStrictly: true,
              onlyCurrent: false
            }" row-key="id" @page-change="handlePageChange" @page-size-change="handlePageSizeChange" v-model:selectedKeys="selectedRowKeys">
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
                  <a-button type="text" @click="toggleFavoriteStatus(record)" :title="record.is_favorite === 1 ? '取消收藏' : '收藏'">
                    <template #icon>
                      <icon-star-fill v-if="record.is_favorite === 1" />
                      <icon-star v-else />
                    </template>
                  </a-button>
                  <a-button
                    type="text"
                    :loading="refreshingArticleIds.includes(String(record.id))"
                    @click="refreshSingleArticle(record)"
                  >
                    <template #icon><icon-refresh /></template>
                  </a-button>
                  <a-button type="text" status="danger" @click="deleteArticle(record.id)">
                    <template #icon><icon-delete /></template>
                  </a-button>
                </a-space>
              </template>
            </a-table>
          </div>


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
          <a-modal v-model:visible="featuredArticleModalVisible" title="添加精选文章">
            <a-form>
              <a-form-item label="文章链接">
                <div class="featured-url-input-wrapper">
                  <a-input
                    v-model="featuredArticleUrl"
                    placeholder="请输入微信公众号文章链接"
                    allow-clear
                  />
                  <div class="featured-url-example">eg：https://mp.weixin.qq.com/s/xxxxx</div>
                </div>
              </a-form-item>
            </a-form>
            <template #footer>
              <a-button @click="featuredArticleModalVisible = false">取消</a-button>
              <a-button type="primary" @click="handleAddFeaturedArticle">添加</a-button>
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
            <div ref="shadowContainer" style="width: 100%; height: auto;"></div>

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
import { ref, onMounted, h, nextTick, watch, computed } from 'vue'
import axios from 'axios'
import { IconApps, IconAtt, IconDelete, IconEdit, IconEye, IconRefresh, IconScan, IconWeiboCircleFill, IconWifi, IconCode, IconCheck, IconClose, IconStop, IconPlayArrow, IconCopy, IconPlus, IconDown, IconExport, IconImport, IconShareExternal, IconStar, IconStarFill, IconLink, IconMenuFold, IconMenuUnfold } from '@arco-design/web-vue/es/icon'
import { getArticles, deleteArticle as deleteArticleApi, ClearArticle, ClearDuplicateArticle, getArticleDetail, getRefreshArticleTaskStatus, refreshArticle as refreshArticleApi, toggleArticleFavoriteStatus, toggleArticleReadStatus } from '@/api/article'
import { ExportOPML, ExportMPS, ImportMPS } from '@/api/export'
import ExportModal from '@/components/ExportModal.vue'
import { addFeaturedArticle, getFeaturedArticleTaskStatus, getSubscriptions, UpdateMps, toggleMpStatus as toggleMpStatusApi } from '@/api/subscription'
import { inject } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { formatDateTime, formatTimestamp } from '@/utils/date'
import router from '@/router'
import { deleteMpApi } from '@/api/subscription'
import TextIcon from '@/components/TextIcon.vue'
import { ProxyImage } from '@/utils/constants'

const articles = ref([])
const FEATURED_MP_ID = 'MP_WXS_FEATURED_ARTICLES'
const FEATURED_MP_NAME = '精选文章'
const loading = ref(false)
const mpList = ref([])
const mpLoading = ref(false)
const activeMpId = ref('')
const siderCollapsed = ref(false)
const exportModal = ref()
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
const mpFilterType = ref('active') // 'active' | 'disabled' | 'all'
const searchText = ref('')
const filterStatus = ref('')
const mpSearchText = ref('')
const onlyFavorite = ref(false)
const featuredArticleModalVisible = ref(false)
const featuredArticleUrl = ref('')

const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
  showTotal: true,
  showJumper: true,
  showPageSize: true,
  pageSizeOptions: [10, 20, 50, 100]
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
    title: '已阅',
    dataIndex: 'is_read',
    width: '100',
    render: ({ record }) => {
      const isRead = record.is_read === 1;
      return h('div', { 
        style: { 
          display: 'flex', 
          alignItems: 'center', 
          cursor: 'pointer',
          color: isRead ? 'var(--color-success)' : 'var(--color-text-3)'
        },
        onClick: () => toggleReadStatus(record)
      }, [
        h(isRead ? IconCheck : IconClose, { 
          style: { marginRight: '4px' } 
        }),
        h('span', { 
          style: { fontSize: '12px' } 
        }, isRead ? '已读' : '未读')
      ]);
    }
  },
  {
    title: '文章标题',
    dataIndex: 'title',
    width: 700,
    render: ({ record }) => h('a', {
      href: issourceUrl.value ? record.url || '#' : "/views/article/" + record.id,
      title: record.title,
      target: '_blank',
      style: { 
        color: 'var(--color-text-1)',
        textDecoration: record.is_read === 1 ? 'line-through' : 'none',
        opacity: record.is_read === 1 ? 0.7 : 1
      }
    }, record.title)
  },
  {
    title: '公众号',
    dataIndex: 'mp_id',
    width: '120',
    ellipsis: true,
    render: ({ record }) => {
      const mp = mpList.value.find(item => item.id === record.mp_id);
      return h('a', {
        style: {
          color: 'var(--color-link)',
          cursor: 'pointer',
          textDecoration: 'none'
        },
        onClick: (e: MouseEvent) => {
          e.preventDefault()
          handleMpClick(record.mp_id)
        }
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
      { style: { color: 'rgb(var(--color-text-3))', fontSize: '12px' } },
      formatTimestamp(record.publish_time)
    )
  },
  {
    title: '操作',
    dataIndex: 'actions',
    width: 180,
    align: 'center',
    slotName: 'actions'
  }
]

const handleMpPageChange = (page: number, pageSize: number) => {
  mpPagination.value.current = page
  mpPagination.value.pageSize = pageSize
  fetchMpList()
}

const handleMpSearch = () => {
  mpPagination.value.current = 1
  fetchMpList()
}
const rssFormat = ref('atom')
const activeFeed = ref({
  id: "",
  name: "全部",
})

const canManageMp = (mpId: string) => mpId !== '' && mpId !== FEATURED_MP_ID

const showAddFeaturedArticleModal = () => {
  featuredArticleUrl.value = ''
  featuredArticleModalVisible.value = true
}

const handleAddFeaturedArticle = async () => {
  const url = featuredArticleUrl.value.trim()
  if (!url) {
    Message.warning('请输入文章链接')
    return
  }
  if (!url.includes('mp.weixin.qq.com/s/')) {
    Message.warning('请输入有效的公众号文章链接')
    return
  }

  try {
    const res = await addFeaturedArticle({ url })
    const taskId = res?.task_id
    Message.success(res?.message || '已开始添加/抓取，请稍后刷新查看结果')
    featuredArticleModalVisible.value = false
    if (!taskId) {
      return
    }

    for (let i = 0; i < 15; i++) {
      await new Promise((resolve) => setTimeout(resolve, 2000))
      try {
        const task = await getFeaturedArticleTaskStatus(taskId)
        if (task?.status === 'success') {
          Message.success(task?.message || '精选文章添加成功')
          await fetchMpList()
          handleMpClick(FEATURED_MP_ID)
          return
        }
        if (task?.status === 'failed') {
          Message.error(task?.message || '添加精选文章失败')
          return
        }
      } catch (error) {
        console.error('查询精选文章任务失败:', error)
      }
    }

    Message.info('导入任务仍在执行，请稍后手动刷新查看结果')
  } catch (error) {
    Message.error(String(error || '添加精选文章失败'))
  }
}

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
      mp_id: activeMpId.value,
      only_favorite: onlyFavorite.value
    })

    const res = await getArticles({
      page: pagination.value.current - 1,
      pageSize: pagination.value.pageSize,
      search: searchText.value,
      status: filterStatus.value,
      mp_id: activeMpId.value,
      only_favorite: onlyFavorite.value
    })

    // 确保数据包含必要字段
    articles.value = (res.list || []).map(item => ({
      ...item,
      mp_name: item.mp_name || item.account_name || '未知公众号',
      publish_time: item.publish_time || item.create_time || '-',
      url: item.url || "https://mp.weixin.qq.com/s/" + item.id,
      is_favorite: item.is_favorite === 1 ? 1 : 0
    }))
    pagination.value.total = res.total || 0
  } catch (error) {
    console.error('获取文章列表错误:', error)
    Message.error(error)
  } finally {
    loading.value = false
  }
}
const issourceUrl = ref(false)

// 过滤后的公众号列表
const filteredMpList = computed(() => {
  if (mpFilterType.value === 'all') {
    return mpList.value
  }
  if (mpFilterType.value === 'disabled') {
    return mpList.value.filter(item => item.status === 0)
  }
  // 'active' - 默认只显示启用的和"全部"选项
  return mpList.value.filter(item => item.status !== 0 || item.id === '')
})

// 从 localStorage 读取 issourceUrl 值
const initIssourceUrl = () => {
  const savedValue = localStorage.getItem('issourceUrl')
  if (savedValue !== null) {
    issourceUrl.value = savedValue === 'true'
  }
}

// 监听 issourceUrl 变化并保存到 localStorage
watch(issourceUrl, (newValue) => {
  localStorage.setItem('issourceUrl', newValue.toString())
}, { immediate: false })
const handlePageChange = (page: number) => {
  console.log('分页事件触发:', { page })
  pagination.value.current = page
  fetchArticles()
}

const handlePageSizeChange = (pageSize: number) => {
  console.log('页面大小改变:', { pageSize })
  pagination.value.pageSize = pageSize
  pagination.value.current = 1 // 切换页面大小时重置到第一页
  fetchArticles()
}

const handleSearch = () => {
  pagination.value.current = 1
  fetchArticles()
}

const handleFavoriteFilterChange = (value: boolean | (string | number | boolean)[]) => {
  onlyFavorite.value = Array.isArray(value) ? value.length > 0 : Boolean(value)
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
      const response = await ImportMPS(formData);
      Message.info(response?.message || "导入成功");
    };
    input.click();
  } catch (error) {
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
 return ProxyImage(record.content)
 }
const viewArticle = async (record: any, action_type: number = 0) => {
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
    
    // 创建或更新 Shadow DOM
    await nextTick()
    createShadowHost()
    
    // 自动标记为已读（仅在查看当前文章时，不是上一篇/下一篇）
    if (action_type === 0 && record.is_read !== 1) {
      await toggleReadStatus(record)
    }
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
const shadowContainer = ref()
const refreshingArticleIds = ref<string[]>([])

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

const pollRefreshArticleTask = async (taskId: string) => {
  for (let i = 0; i < 15; i++) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    try {
      const task = await getRefreshArticleTaskStatus(taskId)
      if (task?.status === 'success') {
        Message.success(task?.message || '文章刷新成功')
        await fetchArticles()
        return
      }
      if (task?.status === 'failed') {
        Message.error(task?.message || '文章刷新失败')
        return
      }
    } catch (error) {
      console.error('查询文章刷新任务失败:', error)
    }
  }

  Message.info('刷新任务仍在执行，请稍后手动刷新列表查看结果')
}

const refreshSingleArticle = async (record: any) => {
  const articleId = String(record.id)
  if (refreshingArticleIds.value.includes(articleId)) {
    return
  }

  refreshingArticleIds.value = [...refreshingArticleIds.value, articleId]
  try {
    const res = await refreshArticleApi(record.id)
    const taskId = res?.task_id
    Message.success(res?.message || '已开始刷新，请稍后查看')
    if (taskId) {
      await pollRefreshArticleTask(taskId)
    }
  } catch (error) {
    console.error('刷新文章失败:', error)
    Message.error(String(error || '刷新文章失败'))
  } finally {
    refreshingArticleIds.value = refreshingArticleIds.value.filter((id) => id !== articleId)
  }
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

const handleExportShow = async () => {
  let mp_id=activeFeed.value?.id
  let ids=selectedRowKeys.value
  let mp_name=activeFeed.value?.name || activeFeed.value?.mp_name || '全部'
  exportModal.value.show(mp_id,ids,mp_name)
}


onMounted(() => {
  console.log('组件挂载，开始获取数据')
  initIssourceUrl() // 初始化 issourceUrl 值

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
      pageSize: mpPagination.value.pageSize,
      kw: mpSearchText.value
    })

    mpList.value = res.list.map(item => ({
      id: item.id || item.mp_id,
      name: item.name || item.mp_name,
      avatar: item.avatar || item.mp_cover || '',
      mp_intro: item.mp_intro || item.mp_intro || '',
      article_count: item.article_count || 0,
      status: item.status ?? 1
    }))
    // 添加'全部'选项 - 只在没有搜索时显示
    if (!mpSearchText.value) {
      mpList.value.unshift({
        id: '',
        name: '全部',
        avatar: '/static/logo.svg',
        mp_intro: '显示所有公众号文章',
        article_count: res.total || 0,
        status: 1
      });
    }
    mpPagination.value.total = res.total || 0
  } catch (error) {
    console.error('获取公众号列表错误:', error)
  } finally {
    mpLoading.value = false
  }
}

const copyMpId = async (mpId: string) => {
  try {
    await navigator.clipboard.writeText(mpId);
    Message.success('MP ID 已复制到剪贴板');
  } catch (error) {
    // 如果 clipboard API 不可用，使用传统方法
    const textArea = document.createElement('textarea');
    textArea.value = mpId;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      Message.success('MP ID 已复制到剪贴板');
    } catch (err) {
      Message.error('复制失败，请手动复制');
      console.error('复制失败:', err);
    }
    document.body.removeChild(textArea);
  }
}

const deleteMp = async (mpId: string) => {
  if (!canManageMp(mpId)) {
    return
  }
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

const toggleMpStatus = async (mpId: string, newStatus: number) => {
  if (!canManageMp(mpId)) {
    return
  }
  try {
    await toggleMpStatusApi(mpId, newStatus);
    Message.success(newStatus === 0 ? '公众号已禁用' : '公众号已启用');
    // 更新本地数据
    const index = mpList.value.findIndex(item => item.id === mpId);
    if (index !== -1) {
      mpList.value[index].status = newStatus;
    }
  } catch (error) {
    console.error('更新公众号状态失败:', error);
    Message.error('更新公众号状态失败');
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

// 创建 Shadow DOM 隔离容器
const createShadowHost = () => {
  if (!shadowContainer.value) return;
  
  // 清空容器
  shadowContainer.value.innerHTML = '';
  
  // 创建 Shadow Host
  const shadowHost = document.createElement('div');
  shadowHost.style.width = '100%';
  shadowHost.style.height = 'auto';
  
  // 创建 Shadow Root
  const shadowRoot = shadowHost.attachShadow({ mode: 'open' });
  
  // 添加基础样式到 Shadow DOM
  const style = document.createElement('style');
  style.textContent = `
    :host {
      display: block;
      width: 100%;
      height: auto;
    }
    img {
      max-width: 100% !important;
      height: auto !important;
      display: block;
      margin: 0 auto;
    }
    iframe {
      width: 100% !important;
      border: none !important;
    }
    p {
      margin: 1em 0;
      line-height: 1.6;
    }
    * {
      box-sizing: border-box;
    }
  `;
  shadowRoot.appendChild(style);
  
  // 创建内容容器
  const contentDiv = document.createElement('div');
  contentDiv.innerHTML = currentArticle.value.content || '';
  shadowRoot.appendChild(contentDiv);
  
  // 将 Shadow Host 添加到容器中
  shadowContainer.value.appendChild(shadowHost);
};

// 切换文章阅读状态
const toggleReadStatus = async (record: any) => {
  try {
    const newReadStatus = record.is_read === 1 ? false : true;
    await toggleArticleReadStatus(record.id, newReadStatus);
    
    // 更新本地数据
    const index = articles.value.findIndex(item => item.id === record.id);
    if (index !== -1) {
      articles.value[index].is_read = newReadStatus ? 1 : 0;
    }
    
    Message.success(`文章已标记为${newReadStatus ? '已读' : '未读'}`);
  } catch (error) {
    console.error('更新阅读状态失败:', error);
    Message.error('更新阅读状态失败');
  }
};

const toggleFavoriteStatus = async (record: any) => {
  try {
    const newFavoriteStatus = record.is_favorite === 1 ? false : true
    await toggleArticleFavoriteStatus(record.id, newFavoriteStatus)

    const index = articles.value.findIndex(item => item.id === record.id)
    if (index !== -1) {
      articles.value[index].is_favorite = newFavoriteStatus ? 1 : 0
    }

    Message.success(newFavoriteStatus ? '收藏成功' : '已取消收藏')

    if (onlyFavorite.value && !newFavoriteStatus) {
      pagination.value.current = 1
      fetchArticles()
    }
  } catch (error) {
    console.error('更新收藏状态失败:', error)
    Message.error('更新收藏状态失败')
  }
}
</script>

<style scoped>
.article-list {
  /* height: calc(100vh - 186px); */
  width: 100%;
  min-width: 0;
}

:deep(.article-list-spin.arco-spin) {
  display: block;
  width: 100%;
}

:deep(.article-list-spin .arco-spin-children) {
  width: 100%;
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
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.article-table-scroll {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
}

:deep(.article-table-scroll .arco-table) {
  min-width: 1100px;
}

.search-input {
  flex: 1;
  min-width: 0;
  max-width: calc(100% - 140px);
}

.favorite-filter {
  flex: 0 0 auto;
  white-space: nowrap;
}

.featured-url-example {
  margin-top: 8px;
  color: var(--color-text-3);
  font-size: 12px;
}

.featured-url-input-wrapper {
  width: 100%;
}

:deep(.arco-table-th-item) {
  justify-content: center;
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
