<template>
  <div class="products-page" v-loading="loading">
    <header class="page-head">
      <div>
        <h2>产品矩阵</h2>
        <span>{{ registry?.updated_at ? `更新于 ${formatTime(registry.updated_at)}` : '产品注册表' }}</span>
      </div>
      <div class="head-actions">
        <el-button type="primary" :icon="Plus" @click="openCreateProduct">新建产品</el-button>
        <el-tooltip content="刷新产品状态" placement="bottom">
          <el-button :icon="Refresh" :loading="loading" aria-label="刷新产品状态" @click="loadProducts" />
        </el-tooltip>
      </div>
    </header>

    <section class="registry-metrics" aria-label="产品注册统计">
      <div><span>产品</span><strong>{{ registry?.summary.total || 0 }}</strong></div>
      <div><span>在线系统</span><strong>{{ registry?.summary.online || 0 }}</strong></div>
      <div><span>离线系统</span><strong>{{ registry?.summary.offline || 0 }}</strong></div>
      <div><span>项目绑定</span><strong>{{ registry?.summary.project_bindings || 0 }}</strong></div>
    </section>

    <section v-if="leadProduct" class="portfolio-leadership">
      <div class="portfolio-lead-copy">
        <span>产品体系牵引</span>
        <h3>{{ leadProduct.name }}</h3>
        <p>{{ leadProduct.positioning || leadProduct.description }}</p>
      </div>
      <div class="portfolio-flow" aria-label="产品体系链路">
        <div v-for="stage in portfolioStages" :key="stage.label">
          <strong>{{ stage.label }}</strong>
          <small>{{ stage.summary }}</small>
        </div>
      </div>
    </section>

    <section v-if="projectContextId" class="project-binding-band">
      <div>
        <span>当前项目</span>
        <strong>{{ currentProject?.name || projectContextId }}</strong>
        <small v-if="selectedProduct">
          {{ bindingForSelected ? `${roleLabel(bindingForSelected.role)} · 已绑定` : `尚未使用 ${selectedProduct.name}` }}
        </small>
      </div>
      <div class="head-actions">
        <el-button text @click="openProject(projectContextId)">返回项目</el-button>
        <el-button
          v-if="selectedProduct?.id !== 'openclaw-3021'"
          :type="bindingForSelected ? 'danger' : 'primary'"
          :plain="Boolean(bindingForSelected)"
          :loading="bindingProduct"
          @click="toggleSelectedBinding"
        >
          {{ bindingForSelected ? '解除绑定' : '绑定到项目' }}
        </el-button>
        <el-tag v-else effect="plain">宿主平台</el-tag>
      </div>
    </section>

    <section v-if="coreProducts.length" class="dependency-band">
      <div class="section-head">
        <h3>核心运行链</h3>
        <el-tag effect="plain">{{ registry?.dependencies.length || 0 }} 项依赖</el-tag>
      </div>
      <div class="core-chain">
        <template v-for="(product, index) in coreProducts" :key="product.id">
          <button type="button" class="chain-product" @click="selectProduct(product)">
            <span>{{ kindLabel(product.kind) }}</span>
            <strong>{{ product.name }}</strong>
            <small>{{ product.runtime?.summary || statusLabel(product.status) }}</small>
          </button>
          <span v-if="index < coreProducts.length - 1" class="chain-arrow">→</span>
        </template>
      </div>
    </section>

    <section v-if="portfolioGroups.length" class="portfolio-modules" aria-label="产品体系模块">
      <div class="section-head">
        <h3>产品体系</h3>
        <span>按平台、能力、业务产品和交付物组织</span>
      </div>
      <div class="portfolio-group-grid">
        <section v-for="group in portfolioGroups" :key="group.key" class="portfolio-group">
          <header>
            <div>
              <span>{{ group.kicker }}</span>
              <h4>{{ group.title }}</h4>
            </div>
            <el-tag effect="plain" size="small">{{ group.products.length }} 项</el-tag>
          </header>
          <div class="portfolio-product-list">
            <button
              v-for="product in group.products"
              :key="product.id"
              type="button"
              class="portfolio-product-card"
              @click="openProductDetail(product)"
            >
              <div class="product-visual" :style="coverStyle(product)">
                <span>{{ product.short_name || product.name.slice(0, 8) }}</span>
              </div>
              <div>
                <strong>{{ product.name }}</strong>
                <small>{{ product.positioning || product.description || '尚未补充产品定位' }}</small>
              </div>
            </button>
          </div>
        </section>
      </div>
    </section>

    <section v-if="featuredProducts.length" class="featured-products" aria-label="主产品展示">
      <div class="section-head">
        <h3>主产品展示</h3>
        <span>真实运行图、体系定位和下一步动作</span>
      </div>
      <div class="featured-grid">
        <article v-for="product in featuredProducts" :key="product.id" class="featured-card">
          <button type="button" class="featured-visual" :style="coverStyle(product)" @click="openProductDetail(product)">
            <span>{{ product.short_name || product.name.slice(0, 8) }}</span>
          </button>
          <div class="featured-copy">
            <div>
              <span>{{ product.category || kindLabel(product.kind) }}</span>
              <h4>{{ product.name }}</h4>
            </div>
            <p>{{ product.positioning || product.description || '尚未补充产品定位。' }}</p>
            <div class="featured-tags">
              <el-tag v-for="item in (product.value_props || product.capabilities || []).slice(0, 3)" :key="item" effect="plain" size="small">{{ item }}</el-tag>
              <span v-if="!(product.value_props || product.capabilities || []).length" class="empty-inline">尚未登记价值说明</span>
            </div>
            <footer>
              <el-tag :type="runtimeTagType(product.runtime?.state)" effect="plain" size="small">{{ runtimeLabel(product.runtime?.state) }}</el-tag>
              <el-button text size="small" @click="openProductDetail(product)">进入详情</el-button>
            </footer>
          </div>
        </article>
      </div>
    </section>

    <section class="evidence-roadmap">
      <div class="evidence-panel">
        <div class="section-head">
          <h3>交付证据</h3>
          <span>{{ evidenceProducts.length }} 项有登记交付物</span>
        </div>
        <div v-if="evidenceProducts.length" class="evidence-product-list">
          <button v-for="product in evidenceProducts" :key="product.id" type="button" @click="openProductDetail(product)">
            <strong>{{ product.name }}</strong>
            <small>待验收 {{ product.delivery_summary?.pending_review || 0 }} · 已验收 {{ product.delivery_summary?.accepted || 0 }}</small>
          </button>
        </div>
        <span v-else class="empty-inline">尚未登记产品交付证据</span>
      </div>
      <div class="roadmap-panel">
        <div class="section-head">
          <h3>产品路线</h3>
          <span>体系化推进顺序</span>
        </div>
        <div class="roadmap-list">
          <article v-for="step in roadmapSteps" :key="step.title">
            <div>
              <strong>{{ step.title }}</strong>
              <small>{{ step.summary }}</small>
            </div>
          </article>
        </div>
      </div>
    </section>

    <main class="registry-layout">
      <section class="product-list">
        <div class="section-head">
          <h3>产品目录管理</h3>
          <el-segmented v-model="kindFilter" :options="kindOptions" size="small" />
        </div>
        <div class="product-grid" role="list" aria-label="产品卡片列表">
          <button
            v-for="product in filteredProducts"
            :key="product.id"
            type="button"
            class="product-card"
            :class="{ selected: selectedProduct?.id === product.id }"
            role="listitem"
            @click="openProductDetail(product)"
          >
            <div class="product-card-visual" :style="coverStyle(product)">
              <span>{{ product.short_name || product.name.slice(0, 8) }}</span>
            </div>
            <header>
              <span class="product-kind">{{ kindLabel(product.kind) }}</span>
              <el-tag :type="runtimeTagType(product.runtime?.state)" effect="plain" size="small">
                {{ runtimeLabel(product.runtime?.state) }}
              </el-tag>
            </header>
            <div class="product-card-title">
              <strong>{{ product.name }}</strong>
              <small>{{ product.version || '未标版本' }} · {{ product.owner || '未分配负责人' }}</small>
            </div>
            <p>{{ product.description || '尚未补充产品说明。' }}</p>
            <dl class="product-card-stats">
              <div><dt>关联项目</dt><dd>{{ product.usage_count || 0 }}</dd></div>
              <div><dt>有效交付</dt><dd>{{ product.delivery_summary?.accepted || 0 }}</dd></div>
              <div><dt>待验收</dt><dd>{{ product.delivery_summary?.pending_review || 0 }}</dd></div>
            </dl>
            <footer>
              <span>{{ product.current_release ? `当前版本 ${product.current_release.version}` : '尚无发布版本' }}</span>
              <span>{{ product.runtime?.summary || statusLabel(product.status) }}</span>
            </footer>
          </button>
        </div>
      </section>

      <aside v-if="selectedProduct" class="product-detail">
        <header>
          <div>
            <span>{{ selectedProduct.category }}</span>
            <h3>{{ selectedProduct.name }}</h3>
          </div>
          <div class="detail-actions">
            <el-button text :icon="Edit" aria-label="编辑产品" @click="openEditProduct">编辑</el-button>
            <el-tag :type="runtimeTagType(selectedProduct.runtime?.state)" effect="plain">
              {{ runtimeLabel(selectedProduct.runtime?.state) }}
            </el-tag>
          </div>
        </header>
        <p>{{ selectedProduct.description }}</p>

        <dl class="product-facts">
          <div><dt>产品标识</dt><dd>{{ selectedProduct.id }}</dd></div>
          <div><dt>版本</dt><dd>{{ selectedProduct.version || '未标版本' }}</dd></div>
          <div><dt>负责人</dt><dd>{{ selectedProduct.owner || '未分配' }}</dd></div>
          <div><dt>运行模式</dt><dd>{{ deploymentModeLabel(selectedProduct.deployment?.mode) }}</dd></div>
        </dl>

        <section>
          <h4>能力</h4>
          <div class="tag-list">
            <el-tag v-for="capability in selectedProduct.capabilities || []" :key="capability" effect="plain" size="small">
              {{ capability }}
            </el-tag>
            <span v-if="!(selectedProduct.capabilities || []).length" class="empty-inline">尚未配置</span>
          </div>
        </section>

        <section>
          <div class="section-title"><h4>项目引用</h4><el-button text size="small" :icon="Connection" @click="openBindingDialog">关联项目</el-button></div>
          <div v-if="selectedProduct.project_references?.length" class="detail-list">
            <div v-for="reference in selectedProduct.project_references" :key="reference.project_id" class="linked-row">
              <button type="button" @click="openProject(reference.project_id)">
                <strong>{{ reference.project_name }}</strong>
                <small>{{ roleLabel(reference.role) }} · {{ reference.status }}</small>
              </button>
              <el-button text type="danger" size="small" @click="removeProductBinding(reference.project_id)">解除</el-button>
            </div>
          </div>
          <span v-else class="empty-inline">尚未绑定项目</span>
        </section>

        <section>
          <div class="section-title"><h4>交付物</h4><el-button text size="small" :icon="DocumentAdd" @click="openDeliverableDialog">登记</el-button></div>
          <div v-if="deliverables.length" class="detail-list">
            <div v-for="deliverable in deliverables" :key="deliverable.id" class="delivery-row">
              <div>
                <strong>{{ deliverable.title }}</strong>
                <small>{{ deliverableKindLabel(deliverable.kind) }} · {{ deliverableStatusLabel(deliverable.status) }} · {{ formatTime(deliverable.created_at || '') }}</small>
              </div>
              <div v-if="deliverable.status === 'draft'" class="row-actions">
                <el-button text type="success" size="small" @click="openReviewDialog(deliverable, true)">验收</el-button>
                <el-button text type="danger" size="small" @click="openReviewDialog(deliverable, false)">退回</el-button>
              </div>
            </div>
          </div>
          <span v-else class="empty-inline">该产品尚未登记交付物</span>
        </section>

        <section>
          <div class="section-title"><h4>发布记录</h4><el-button text size="small" :icon="Promotion" @click="openReleaseDialog">创建版本</el-button></div>
          <div v-if="releases.length" class="detail-list">
            <div v-for="release in releases" :key="release.id">
              <strong>{{ release.version }}</strong>
              <small>{{ release.environment }} · {{ releaseStatusLabel(release.status) }}{{ release.deployment_url ? ` · ${release.deployment_url}` : '' }}</small>
            </div>
          </div>
          <span v-else class="empty-inline">尚未发布</span>
        </section>

        <section>
          <div class="section-title"><h4>运行实例</h4><div class="row-actions"><el-tooltip content="同步已配置健康地址的实例" placement="top"><el-button text size="small" :icon="Refresh" :loading="syncingHealth" aria-label="同步运行健康" @click="syncAllRuntimeHealth" /></el-tooltip><el-button text size="small" :icon="Monitor" @click="openRuntimeDialog()">登记实例</el-button></div></div>
          <div v-if="runtimeInstances.length" class="detail-list">
            <div v-for="runtime in runtimeInstances" :key="runtime.id" class="delivery-row">
              <div>
                <strong>{{ runtime.name }}</strong>
                <small>{{ runtime.environment }} · {{ runtimeLabel(runtime.state) }}{{ runtime.version ? ` · ${runtime.version}` : '' }}{{ runtime.last_observed_at ? ` · ${formatTime(runtime.last_observed_at)}` : '' }}</small>
              </div>
              <div class="row-actions">
                <el-tooltip :content="runtime.health_url ? '同步健康状态' : '请先配置健康检查地址'" placement="top"><el-button text size="small" :icon="Refresh" :disabled="!runtime.health_url" :loading="syncingRuntimeId === runtime.id" aria-label="同步实例健康" @click="syncRuntimeHealth(runtime)" /></el-tooltip>
                <el-button text size="small" @click="openRuntimeDialog(runtime)">编辑</el-button>
                <el-button text type="danger" size="small" @click="removeRuntime(runtime)">移除</el-button>
              </div>
            </div>
          </div>
          <span v-else class="empty-inline">尚未登记运行实例</span>
        </section>

        <section>
          <h4>最近活动</h4>
          <div v-if="timeline.length" class="timeline-list">
            <div v-for="event in timeline" :key="event.id"><strong>{{ eventLabel(event.event_type) }}</strong><small>{{ formatTime(event.created_at || '') }}</small></div>
          </div>
          <span v-else class="empty-inline">尚无产品活动</span>
        </section>
      </aside>
    </main>

    <el-dialog v-model="productDialogVisible" :title="productDialogMode === 'create' ? '新建产品' : '编辑产品'" width="min(680px, 94vw)" @closed="resetProductForm">
      <el-form label-position="top" class="dialog-form">
        <div class="form-grid">
          <el-form-item label="产品标识" required><el-input v-model.trim="productForm.id" :disabled="productDialogMode === 'edit'" placeholder="例如 digital-wargame" /></el-form-item>
          <el-form-item label="产品名称" required><el-input v-model.trim="productForm.name" /></el-form-item>
          <el-form-item label="产品类型"><el-select v-model="productForm.kind"><el-option v-for="option in productKindOptions" :key="option.value" :label="option.label" :value="option.value" /></el-select></el-form-item>
          <el-form-item label="生命周期"><el-select v-model="productForm.status"><el-option v-for="option in productStatusOptions" :key="option.value" :label="option.label" :value="option.value" /></el-select></el-form-item>
          <el-form-item label="产品分类"><el-input v-model.trim="productForm.category" /></el-form-item>
          <el-form-item label="负责人智能体"><el-input v-model.trim="productForm.owner" placeholder="例如 optimus" /></el-form-item>
          <el-form-item label="当前版本"><el-input v-model.trim="productForm.version" placeholder="例如 v1.0.0" /></el-form-item>
          <el-form-item label="代码仓库"><el-input v-model.trim="productForm.repository" /></el-form-item>
        </div>
        <el-form-item label="产品说明"><el-input v-model="productForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="能力标签"><el-input v-model="productForm.capabilities" placeholder="使用逗号分隔" /></el-form-item>
        <el-form-item label="产品标签"><el-input v-model="productForm.tags" placeholder="使用逗号分隔" /></el-form-item>
        <div class="form-grid">
          <el-form-item label="部署模式"><el-select v-model="productForm.deployment_mode"><el-option v-for="option in deploymentModeOptions" :key="option.value" :label="option.label" :value="option.value" /></el-select></el-form-item>
          <el-form-item label="默认访问地址"><el-input v-model.trim="productForm.public_url" /></el-form-item>
          <el-form-item label="默认主机"><el-input v-model.trim="productForm.host" /></el-form-item>
          <el-form-item label="默认端口"><el-input-number v-model="productForm.port" :min="1" :max="65535" controls-position="right" /></el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button v-if="productDialogMode === 'edit' && canDeleteSelectedProduct" type="danger" text :icon="Delete" :loading="saving" @click="removeSelectedProduct">删除产品</el-button>
        <span class="dialog-spacer" />
        <el-button @click="productDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveProduct">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bindingDialogVisible" title="关联项目" width="min(480px, 94vw)">
      <el-form label-position="top" class="dialog-form">
        <el-form-item label="项目" required><el-select v-model="bindingForm.project_id" filterable><el-option v-for="project in bindableProjects" :key="project.id" :label="project.name" :value="project.id" /></el-select></el-form-item>
        <el-form-item label="关系"><el-select v-model="bindingForm.role"><el-option v-for="option in bindingRoleOptions" :key="option.value" :label="option.label" :value="option.value" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="bindingDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveProductBinding">关联</el-button></template>
    </el-dialog>

    <el-dialog v-model="deliverableDialogVisible" title="登记交付物" width="min(560px, 94vw)" @closed="resetDeliverableForm">
      <el-form label-position="top" class="dialog-form">
        <div class="form-grid"><el-form-item label="交付物标题" required><el-input v-model.trim="deliverableForm.title" /></el-form-item><el-form-item label="类型"><el-select v-model="deliverableForm.kind"><el-option v-for="option in deliverableKindOptions" :key="option.value" :label="option.label" :value="option.value" /></el-select></el-form-item></div>
        <div class="form-grid"><el-form-item label="关联项目"><el-select v-model="deliverableForm.project_id" clearable><el-option v-for="project in selectedProduct?.project_references || []" :key="project.project_id" :label="project.project_name" :value="project.project_id" /></el-select></el-form-item><el-form-item label="产生智能体"><el-input v-model.trim="deliverableForm.produced_by_agent_id" /></el-form-item></div>
        <el-form-item label="产物地址"><el-input v-model.trim="deliverableForm.uri" /></el-form-item>
        <div class="form-grid"><el-form-item label="版本"><el-input v-model.trim="deliverableForm.version" /></el-form-item><el-form-item label="内容哈希"><el-input v-model.trim="deliverableForm.content_hash" /></el-form-item></div>
        <el-form-item label="说明"><el-input v-model="deliverableForm.summary" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="deliverableDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveDeliverable">登记</el-button></template>
    </el-dialog>

    <el-dialog v-model="reviewDialogVisible" :title="reviewForm.accepted ? '验收交付物' : '退回交付物'" width="min(480px, 94vw)">
      <el-form label-position="top" class="dialog-form"><el-form-item label="验收智能体" required><el-input v-model.trim="reviewForm.reviewed_by_agent_id" /></el-form-item><el-form-item label="说明"><el-input v-model="reviewForm.review_note" type="textarea" :rows="3" /></el-form-item></el-form>
      <template #footer><el-button @click="reviewDialogVisible = false">取消</el-button><el-button :type="reviewForm.accepted ? 'success' : 'danger'" :loading="saving" @click="saveReview">{{ reviewForm.accepted ? '验收通过' : '确认退回' }}</el-button></template>
    </el-dialog>

    <el-dialog v-model="releaseDialogVisible" title="创建发布版本" width="min(560px, 94vw)" @closed="resetReleaseForm">
      <el-form label-position="top" class="dialog-form">
        <div class="form-grid"><el-form-item label="版本号" required><el-input v-model.trim="releaseForm.version" placeholder="例如 v1.0.0" /></el-form-item><el-form-item label="环境"><el-input v-model.trim="releaseForm.environment" /></el-form-item></div>
        <div class="form-grid"><el-form-item label="发布状态"><el-select v-model="releaseForm.status"><el-option v-for="option in releaseStatusOptions" :key="option.value" :label="option.label" :value="option.value" /></el-select></el-form-item><el-form-item label="发布智能体"><el-input v-model.trim="releaseForm.released_by_agent_id" /></el-form-item></div>
        <el-form-item label="来源交付物"><el-select v-model="releaseForm.source_deliverable_id" clearable><el-option v-for="deliverable in acceptedDeliverables" :key="deliverable.id" :label="deliverable.title" :value="deliverable.id" /></el-select></el-form-item>
        <el-form-item label="部署地址"><el-input v-model.trim="releaseForm.deployment_url" /></el-form-item>
        <el-form-item label="发布说明"><el-input v-model="releaseForm.release_note" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="releaseDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveRelease">创建版本</el-button></template>
    </el-dialog>

    <el-dialog v-model="runtimeDialogVisible" :title="runtimeForm.id ? '编辑运行实例' : '登记运行实例'" width="min(620px, 94vw)" @closed="resetRuntimeForm">
      <el-form label-position="top" class="dialog-form">
        <div class="form-grid"><el-form-item label="实例名称" required><el-input v-model.trim="runtimeForm.name" /></el-form-item><el-form-item label="环境"><el-input v-model.trim="runtimeForm.environment" /></el-form-item></div>
        <div class="form-grid"><el-form-item label="状态"><el-select v-model="runtimeForm.state"><el-option v-for="option in runtimeStateOptions" :key="option.value" :label="option.label" :value="option.value" /></el-select></el-form-item><el-form-item label="运行版本"><el-input v-model.trim="runtimeForm.version" /></el-form-item></div>
        <el-form-item label="关联发布版本"><el-select v-model="runtimeForm.release_id" clearable><el-option v-for="release in releases" :key="release.id" :label="release.version" :value="release.id" /></el-select></el-form-item>
        <div class="form-grid"><el-form-item label="设备"><el-input v-model.trim="runtimeForm.device" /></el-form-item><el-form-item label="主机"><el-input v-model.trim="runtimeForm.host" /></el-form-item><el-form-item label="端口"><el-input-number v-model="runtimeForm.port" :min="1" :max="65535" controls-position="right" /></el-form-item></div>
        <el-form-item label="访问地址"><el-input v-model.trim="runtimeForm.public_url" /></el-form-item>
        <el-form-item label="健康检查地址"><el-input v-model.trim="runtimeForm.health_url" /></el-form-item>
        <el-form-item label="状态说明"><el-input v-model="runtimeForm.summary" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="runtimeDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveRuntime">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Connection, Delete, DocumentAdd, Edit, Monitor, Plus, Promotion, Refresh } from '@element-plus/icons-vue'
import { getProjects, type Project } from '@/api/projects'
import {
  bindProductToProject,
  createProduct,
  createProductRelease,
  createProductRuntimeInstance,
  deleteProduct,
  deleteProductRuntimeInstance,
  downloadProductAsset,
  getProductDeliverables,
  getProductRegistry,
  getProductReleases,
  getProductRuntimeInstances,
  getProductTimeline,
  reviewProductDeliverable,
  submitProductDeliverable,
  syncProductRuntimeHealth,
  syncProductRuntimeInstanceHealth,
  unbindProductFromProject,
  updateProduct,
  updateProductRuntimeInstance,
  type ProductDeliverable,
  type ProductEvent,
  type ProductRelease,
  type ProductRuntimeInstance,
  type ProjectProductBinding,
  type RegisteredProduct,
  type ProductRegistryResponse
} from '@/api/products'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const bindingProduct = ref(false)
const syncingHealth = ref(false)
const syncingRuntimeId = ref('')
const registry = ref<ProductRegistryResponse>()
const selectedProduct = ref<RegisteredProduct>()
const deliverables = ref<ProductDeliverable[]>([])
const releases = ref<ProductRelease[]>([])
const runtimeInstances = ref<ProductRuntimeInstance[]>([])
const timeline = ref<ProductEvent[]>([])
const allProjects = ref<Project[]>([])
const currentProject = ref<Project>()
const coverUrls = ref<Record<string, string>>({})
const kindFilter = ref('all')
const productDialogVisible = ref(false)
const productDialogMode = ref<'create' | 'edit'>('create')
const bindingDialogVisible = ref(false)
const deliverableDialogVisible = ref(false)
const reviewDialogVisible = ref(false)
const releaseDialogVisible = ref(false)
const runtimeDialogVisible = ref(false)
const reviewDeliverable = ref<ProductDeliverable>()

const kindOptions = [
  { label: '全部', value: 'all' },
  { label: '运行系统', value: 'runtime' },
  { label: '业务产品', value: 'offering' }
]
const productKindOptions = [
  { label: '平台', value: 'platform' }, { label: '服务', value: 'service' },
  { label: '仿真系统', value: 'simulation' }, { label: '业务产品', value: 'offering' }
]
const productStatusOptions = [
  { label: '规划中', value: 'planning' }, { label: '研发中', value: 'developing' },
  { label: '运行中', value: 'active' }, { label: '已归档', value: 'archived' }
]
const deploymentModeOptions = [
  { label: '独立部署', value: 'standalone' }, { label: '内嵌服务', value: 'embedded-planning-situation' },
  { label: '实体产品', value: 'physical' }, { label: '待部署', value: 'planned' }
]
const bindingRoleOptions = [
  { label: '主产品', value: 'primary' }, { label: '产出产品', value: 'produces' },
  { label: '所有者', value: 'owns' }, { label: '升级对象', value: 'upgrade' },
  { label: '维护对象', value: 'maintenance' }, { label: '使用', value: 'uses' },
  { label: '规划器', value: 'planner' }, { label: '仿真器', value: 'simulator' }
]
const deliverableKindOptions = [
  { label: '源代码', value: 'source_code' }, { label: '服务', value: 'service' }, { label: '文档', value: 'document' },
  { label: '模型', value: 'model' }, { label: '数据集', value: 'dataset' }, { label: '想定', value: 'scenario' }, { label: '报告', value: 'report' }
]
const releaseStatusOptions = [
  { label: '待发布', value: 'pending' }, { label: '部署中', value: 'deploying' }, { label: '已生效', value: 'active' },
  { label: '发布失败', value: 'failed' }, { label: '已回滚', value: 'rolled_back' }
]
const runtimeStateOptions = [
  { label: '待部署', value: 'pending' }, { label: '部署中', value: 'deploying' }, { label: '在线', value: 'online' },
  { label: '降级', value: 'degraded' }, { label: '离线', value: 'offline' }, { label: '失败', value: 'failed' }, { label: '已停止', value: 'stopped' }
]

const productForm = ref(emptyProductForm())
const bindingForm = ref({ project_id: '', role: 'primary' })
const deliverableForm = ref(emptyDeliverableForm())
const reviewForm = ref({ accepted: true, reviewed_by_agent_id: 'optimus', review_note: '' })
const releaseForm = ref(emptyReleaseForm())
const runtimeForm = ref(emptyRuntimeForm())

const filteredProducts = computed(() => {
  const products = registry.value?.products || []
  if (kindFilter.value === 'offering') return products.filter(row => row.kind === 'offering')
  if (kindFilter.value === 'runtime') return products.filter(row => row.kind !== 'offering')
  return products
})
const coreProducts = computed(() => {
  const order = ['openclaw-3021', 'ai-planning-5130', 'one-sim']
  return order.map(id => registry.value?.products.find(row => row.id === id)).filter(Boolean) as RegisteredProduct[]
})
const projectContextId = computed(() => String(route.query.project_id || ''))
const bindingForSelected = computed<ProjectProductBinding | undefined>(() => currentProject.value?.product_bindings?.find(binding => binding.product_id === selectedProduct.value?.id))
const bindableProjects = computed(() => allProjects.value.filter(project => !selectedProduct.value?.project_references?.some(row => row.project_id === project.id)))
const acceptedDeliverables = computed(() => deliverables.value.filter(row => row.status === 'accepted'))
const canDeleteSelectedProduct = computed(() => Boolean(selectedProduct.value && !['openclaw-3021', 'ai-planning-5130', 'one-sim'].includes(selectedProduct.value.id)))
const leadProduct = computed(() => registry.value?.products.find(row => row.id === 'openclaw-3021') || registry.value?.products.find(row => row.kind === 'platform'))
const portfolioStages = [
  { label: '智能体系统', summary: '组织项目、知识、产品和交付证据' },
  { label: '任务规划', summary: '承接想定、计划生成和重规划' },
  { label: '仿真验证', summary: '形成权威运行记录和实验依据' },
  { label: '产品交付', summary: '沉淀规划书、案例、系统入口和版本' }
]
const roadmapSteps = [
  { title: '体系牵引', summary: 'OpenClaw 统一纳管产品、项目、运行状态和交付证据。' },
  { title: '能力产品化', summary: '智能筹划和兵棋仿真作为核心能力产品独立展示。' },
  { title: '业务产品沉淀', summary: '本体筹划、电子化兵棋、智能兵棋承接具体场景和交付。' },
  { title: '证据验收', summary: '规划书、截图、视频、版本和运行记录进入可追溯交付链。' }
]
const portfolioGroupDefs = [
  { key: 'platform', title: '总体牵引平台', kicker: 'Core', match: (product: RegisteredProduct) => product.id === 'openclaw-3021' || product.portfolio_group === 'platform' },
  { key: 'capability', title: '规划与仿真能力', kicker: 'Capability', match: (product: RegisteredProduct) => ['ai-planning-5130', 'one-sim'].includes(product.id) || product.portfolio_group === 'capability' },
  { key: 'business', title: '业务产品', kicker: 'Product', match: (product: RegisteredProduct) => product.kind === 'offering' || product.portfolio_group === 'business' },
  { key: 'documented', title: '文档与案例牵引', kicker: 'Evidence', match: (product: RegisteredProduct) => Boolean(product.delivery_summary?.total || product.document_links?.length || product.portfolio_group === 'documented') }
]
const portfolioGroups = computed(() => {
  const products = registry.value?.products || []
  const seen = new Set<string>()
  return portfolioGroupDefs.map(group => {
    const grouped = products
      .filter(product => group.match(product))
      .filter(product => {
        if (group.key !== 'documented' && seen.has(product.id)) return false
        if (group.key !== 'documented') seen.add(product.id)
        return true
      })
      .sort((a, b) => (a.display_order ?? 999) - (b.display_order ?? 999) || a.name.localeCompare(b.name, 'zh-CN'))
    return { ...group, products: grouped }
  }).filter(group => group.products.length)
})
const featuredProducts = computed(() => {
  const priority = ['ai-planning-5130', 'one-sim', 'knowledge-ontology-planning-system', 'openclaw-3021']
  const products = registry.value?.products || []
  return priority.map(id => products.find(product => product.id === id)).filter(Boolean) as RegisteredProduct[]
})
const evidenceProducts = computed(() => (registry.value?.products || [])
  .filter(product => product.delivery_summary?.total || product.document_links?.length)
  .sort((a, b) => (b.delivery_summary?.pending_review || 0) - (a.delivery_summary?.pending_review || 0))
  .slice(0, 5))

function emptyProductForm() {
  return { id: '', name: '', kind: 'offering', category: '', description: '', version: '', status: 'planning', owner: '', repository: '', capabilities: '', tags: '', deployment_mode: 'planned', device: '', host: '', port: undefined as number | undefined, public_url: '' }
}
function emptyDeliverableForm() {
  return { title: '', kind: 'document', project_id: '', task_id: '', development_point_id: '', uri: '', content_hash: '', version: '', summary: '', produced_by_agent_id: 'optimus' }
}
function emptyReleaseForm() {
  return { version: selectedProduct.value?.version || '', environment: 'internal', status: 'pending', deployment_url: '', source_deliverable_id: '', released_by_agent_id: 'optimus', release_note: '' }
}
function emptyRuntimeForm() {
  return { id: '', name: '', environment: 'internal', state: 'pending', release_id: '', version: selectedProduct.value?.version || '', device: '', host: '', port: undefined as number | undefined, public_url: '', health_url: '', summary: '' }
}
function splitTags(value: string) {
  return value.split(/[，,\n]/).map(item => item.trim()).filter(Boolean)
}

async function loadProducts() {
  loading.value = true
  try {
    const nextRegistry = await getProductRegistry()
    registry.value = nextRegistry
    await loadCoverImages(nextRegistry.products)
    try {
      const projectResult = await getProjects()
      allProjects.value = projectResult.projects
      currentProject.value = projectResult.projects.find(project => project.id === projectContextId.value)
    } catch {
      allProjects.value = []
      currentProject.value = undefined
    }
    const currentId = selectedProduct.value?.id || String(route.query.product_id || '') || 'openclaw-3021'
    selectedProduct.value = registry.value.products.find(row => row.id === currentId) || registry.value.products[0]
    if (selectedProduct.value) await loadProductEvidence(selectedProduct.value.id)
  } catch {
    ElMessage.error('产品注册表加载失败')
  } finally {
    loading.value = false
  }
}

async function selectProduct(product: RegisteredProduct) {
  selectedProduct.value = product
  await loadProductEvidence(product.id)
}

function openProductDetail(product: RegisteredProduct) {
  router.push({ name: 'ProductDetail', params: { productId: product.id } })
}

function coverStyle(product: RegisteredProduct) {
  if (coverUrls.value[product.id]) return { backgroundImage: `url("${coverUrls.value[product.id]}")` }
  const swatches: Record<string, string> = {
    platform: 'linear-gradient(135deg, #10233f, #21605e)',
    service: 'linear-gradient(135deg, #1f3b4d, #2d6f99)',
    simulation: 'linear-gradient(135deg, #24351f, #5f7b3a)',
    offering: 'linear-gradient(135deg, #423022, #8b6440)'
  }
  return { backgroundImage: swatches[product.kind] || 'linear-gradient(135deg, #263241, #59616f)' }
}

async function loadCoverImages(products: RegisteredProduct[]) {
  const nextUrls: Record<string, string> = {}
  await Promise.all(products.map(async (product) => {
    if (!product.cover_image) return
    try {
      const blob = await downloadProductAsset(product.cover_image)
      nextUrls[product.id] = URL.createObjectURL(blob)
    } catch {
      // Optional covers fall back to deterministic visual swatches.
    }
  }))
  Object.values(coverUrls.value).forEach(url => URL.revokeObjectURL(url))
  coverUrls.value = nextUrls
}

async function loadProductEvidence(productId: string) {
  try {
    const [nextDeliverables, nextReleases, nextRuntimes, nextTimeline] = await Promise.all([
      getProductDeliverables(productId), getProductReleases(productId), getProductRuntimeInstances(productId), getProductTimeline(productId)
    ])
    deliverables.value = nextDeliverables.slice(0, 12)
    releases.value = nextReleases.slice(0, 8)
    runtimeInstances.value = nextRuntimes.slice(0, 8)
    timeline.value = nextTimeline.slice(0, 10)
  } catch {
    deliverables.value = []
    releases.value = []
    runtimeInstances.value = []
    timeline.value = []
  }
}

function openProject(projectId: string) { router.push({ path: '/projects', query: { project_id: projectId } }) }
function defaultBindingRole(productId: string) { return productId === 'ai-planning-5130' ? 'planner' : productId === 'one-sim' ? 'simulator' : 'uses' }

async function toggleSelectedBinding() {
  if (!projectContextId.value || !selectedProduct.value || !currentProject.value) return
  bindingProduct.value = true
  try {
    if (bindingForSelected.value) {
      await ElMessageBox.confirm(`解除“${currentProject.value.name}”与“${selectedProduct.value.name}”的绑定？已有产品数据不会被删除。`, '解除产品绑定', { type: 'warning', confirmButtonText: '解除绑定', cancelButtonText: '取消' })
      currentProject.value = (await unbindProductFromProject(projectContextId.value, selectedProduct.value.id)).project
      ElMessage.success('产品绑定已解除')
    } else {
      currentProject.value = (await bindProductToProject(projectContextId.value, selectedProduct.value.id, { role: defaultBindingRole(selectedProduct.value.id), status: 'bound' })).project
      ElMessage.success('产品已绑定到项目')
    }
    await loadProducts()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('产品绑定更新失败')
  } finally { bindingProduct.value = false }
}

function openCreateProduct() { productDialogMode.value = 'create'; productForm.value = emptyProductForm(); productDialogVisible.value = true }
function openEditProduct() {
  if (!selectedProduct.value) return
  const product = selectedProduct.value
  productDialogMode.value = 'edit'
  productForm.value = { id: product.id, name: product.name, kind: product.kind, category: product.category || '', description: product.description || '', version: product.version || '', status: product.status || 'planning', owner: product.owner || '', repository: product.repository || '', capabilities: (product.capabilities || []).join(', '), tags: (product.tags || []).join(', '), deployment_mode: product.deployment?.mode || 'planned', device: product.deployment?.device || '', host: product.deployment?.host || '', port: product.deployment?.port, public_url: product.deployment?.public_url || '' }
  productDialogVisible.value = true
}
function resetProductForm() { productForm.value = emptyProductForm() }
async function saveProduct() {
  if (!productForm.value.id || !productForm.value.name) return ElMessage.warning('请填写产品标识和产品名称')
  saving.value = true
  const payload = { name: productForm.value.name, kind: productForm.value.kind, category: productForm.value.category, description: productForm.value.description, version: productForm.value.version, status: productForm.value.status, owner: productForm.value.owner, repository: productForm.value.repository, capabilities: splitTags(productForm.value.capabilities), tags: splitTags(productForm.value.tags), dependencies: productDialogMode.value === 'edit' ? selectedProduct.value?.dependencies || [] : [], deployment: { mode: productForm.value.deployment_mode, device: productForm.value.device, host: productForm.value.host, port: productForm.value.port, public_url: productForm.value.public_url } }
  try {
    if (productDialogMode.value === 'create') await createProduct({ id: productForm.value.id, ...payload })
    else await updateProduct(productForm.value.id, payload)
    productDialogVisible.value = false
    await loadProducts()
    selectedProduct.value = registry.value?.products.find(product => product.id === productForm.value.id)
    ElMessage.success(productDialogMode.value === 'create' ? '产品已创建' : '产品信息已更新')
  } catch { ElMessage.error('产品保存失败') } finally { saving.value = false }
}

function openBindingDialog() { bindingForm.value = { project_id: bindableProjects.value[0]?.id || '', role: 'primary' }; bindingDialogVisible.value = true }
async function saveProductBinding() {
  if (!selectedProduct.value || !bindingForm.value.project_id) return ElMessage.warning('请选择项目')
  saving.value = true
  try {
    await bindProductToProject(bindingForm.value.project_id, selectedProduct.value.id, { role: bindingForm.value.role, status: 'bound' })
    bindingDialogVisible.value = false; await loadProducts(); ElMessage.success('项目已关联')
  } catch { ElMessage.error('项目关联失败') } finally { saving.value = false }
}
async function removeProductBinding(projectId: string) {
  if (!selectedProduct.value) return
  try {
    await ElMessageBox.confirm('解除后不会删除产品交付记录，是否继续？', '解除产品绑定', { type: 'warning' })
    await unbindProductFromProject(projectId, selectedProduct.value.id); await loadProducts(); ElMessage.success('项目绑定已解除')
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error('解除绑定失败') }
}

function openDeliverableDialog() { deliverableForm.value = { ...emptyDeliverableForm(), project_id: selectedProduct.value?.project_references?.[0]?.project_id || '' }; deliverableDialogVisible.value = true }
function resetDeliverableForm() { deliverableForm.value = emptyDeliverableForm() }
async function saveDeliverable() {
  if (!selectedProduct.value || !deliverableForm.value.title) return ElMessage.warning('请填写交付物标题')
  saving.value = true
  try {
    await submitProductDeliverable(selectedProduct.value.id, deliverableForm.value)
    deliverableDialogVisible.value = false; await loadProducts(); ElMessage.success('交付物已登记，等待验收')
  } catch { ElMessage.error('交付物登记失败') } finally { saving.value = false }
}
function openReviewDialog(deliverable: ProductDeliverable, accepted: boolean) { reviewDeliverable.value = deliverable; reviewForm.value = { accepted, reviewed_by_agent_id: 'optimus', review_note: '' }; reviewDialogVisible.value = true }
async function saveReview() {
  if (!selectedProduct.value || !reviewDeliverable.value || !reviewForm.value.reviewed_by_agent_id) return ElMessage.warning('请填写验收智能体')
  saving.value = true
  try {
    await reviewProductDeliverable(selectedProduct.value.id, reviewDeliverable.value.id, reviewForm.value)
    reviewDialogVisible.value = false; await loadProducts(); ElMessage.success(reviewForm.value.accepted ? '交付物已验收' : '交付物已退回')
  } catch { ElMessage.error('交付物审核失败') } finally { saving.value = false }
}

function openReleaseDialog() { releaseForm.value = emptyReleaseForm(); releaseDialogVisible.value = true }
function resetReleaseForm() { releaseForm.value = emptyReleaseForm() }
async function saveRelease() {
  if (!selectedProduct.value || !releaseForm.value.version) return ElMessage.warning('请填写版本号')
  if (releaseForm.value.status === 'active' && !releaseForm.value.source_deliverable_id) return ElMessage.warning('生效版本必须关联已验收交付物')
  saving.value = true
  try {
    await createProductRelease(selectedProduct.value.id, releaseForm.value)
    releaseDialogVisible.value = false; await loadProducts(); ElMessage.success('发布版本已创建')
  } catch { ElMessage.error('发布版本创建失败') } finally { saving.value = false }
}

function openRuntimeDialog(runtime?: ProductRuntimeInstance) {
  runtimeForm.value = runtime ? { id: runtime.id, name: runtime.name, environment: runtime.environment, state: runtime.state, release_id: runtime.release_id || '', version: runtime.version || '', device: runtime.device || '', host: runtime.host || '', port: runtime.port || undefined, public_url: runtime.public_url || '', health_url: runtime.health_url || '', summary: runtime.summary || '' } : emptyRuntimeForm()
  runtimeDialogVisible.value = true
}
function resetRuntimeForm() { runtimeForm.value = emptyRuntimeForm() }
async function saveRuntime() {
  if (!selectedProduct.value || !runtimeForm.value.name) return ElMessage.warning('请填写实例名称')
  saving.value = true
  const { id, ...payload } = runtimeForm.value
  try {
    if (id) await updateProductRuntimeInstance(selectedProduct.value.id, id, payload)
    else await createProductRuntimeInstance(selectedProduct.value.id, payload)
    runtimeDialogVisible.value = false; await loadProducts(); ElMessage.success(id ? '运行实例已更新' : '运行实例已登记')
  } catch { ElMessage.error('运行实例保存失败') } finally { saving.value = false }
}
async function removeRuntime(runtime: ProductRuntimeInstance) {
  if (!selectedProduct.value) return
  try {
    await ElMessageBox.confirm(`移除运行实例“${runtime.name}”？历史发布记录不会删除。`, '移除运行实例', { type: 'warning' })
    await deleteProductRuntimeInstance(selectedProduct.value.id, runtime.id); await loadProducts(); ElMessage.success('运行实例已移除')
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error('运行实例移除失败') }
}
async function syncRuntimeHealth(runtime: ProductRuntimeInstance) {
  if (!selectedProduct.value || !runtime.health_url) return ElMessage.warning('请先配置健康检查地址')
  syncingRuntimeId.value = runtime.id
  try {
    const result = await syncProductRuntimeInstanceHealth(selectedProduct.value.id, runtime.id)
    await loadProducts()
    ElMessage.success(`${runtime.name}：${runtimeLabel(result.runtime_instance.state)}`)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '运行健康同步失败')
  } finally { syncingRuntimeId.value = '' }
}
async function syncAllRuntimeHealth() {
  if (!selectedProduct.value) return
  syncingHealth.value = true
  try {
    const result = await syncProductRuntimeHealth(selectedProduct.value.id)
    const synced = result.results.filter(row => row.runtime_instance).length
    const skipped = result.results.filter(row => row.skipped).length
    await loadProducts()
    ElMessage.success(synced ? `已同步 ${synced} 个运行实例${skipped ? `，${skipped} 个未配置检查地址` : ''}` : '没有可同步的运行实例')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '运行健康同步失败')
  } finally { syncingHealth.value = false }
}

async function removeSelectedProduct() {
  if (!selectedProduct.value) return
  try {
    await ElMessageBox.confirm(`删除“${selectedProduct.value.name}”？仅无项目绑定及无交付历史的产品可以删除。`, '删除产品', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await deleteProduct(selectedProduct.value.id); productDialogVisible.value = false; selectedProduct.value = undefined; await loadProducts(); ElMessage.success('产品已删除')
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error('产品删除失败') }
}

function kindLabel(kind?: string) { return ({ platform: '平台', service: '规划服务', simulation: '仿真系统', offering: '业务产品' } as Record<string, string>)[kind || ''] || kind || '产品' }
function statusLabel(status?: string) { return ({ active: '运行中', developing: '开发中', planning: '规划中', archived: '已归档' } as Record<string, string>)[status || ''] || status || '未知' }
function runtimeLabel(state?: string) { return ({ pending: '待部署', deploying: '部署中', online: '在线', degraded: '降级', offline: '离线', failed: '失败', stopped: '已停止', managed: '受管' } as Record<string, string>)[state || ''] || '未知' }
function runtimeTagType(state?: string): 'success' | 'danger' | 'warning' | 'info' { if (state === 'online') return 'success'; if (state === 'offline' || state === 'failed') return 'danger'; if (state === 'degraded' || state === 'deploying') return 'warning'; return 'info' }
function deploymentModeLabel(mode?: string) { return ({ standalone: '独立部署', 'embedded-planning-situation': '内嵌态势会话', physical: '实体产品', planned: '待部署' } as Record<string, string>)[mode || ''] || mode || '未登记' }
function roleLabel(role?: string) { return ({ primary: '主产品', produces: '产出产品', owns: '所有者', upgrade: '升级对象', maintenance: '维护对象', planner: '规划器', simulator: '仿真器', uses: '使用' } as Record<string, string>)[role || ''] || role || '使用' }
function deliverableKindLabel(kind?: string) { return ({ source_code: '代码', service: '服务', document: '文档', model: '模型', dataset: '数据集', scenario: '想定', report: '报告' } as Record<string, string>)[kind || ''] || kind || '交付物' }
function deliverableStatusLabel(status?: string) { return ({ draft: '待验收', accepted: '已验收', rejected: '已退回' } as Record<string, string>)[status || ''] || status || '未知' }
function releaseStatusLabel(status?: string) { return ({ pending: '待发布', deploying: '部署中', active: '已生效', failed: '发布失败', rolled_back: '已回滚' } as Record<string, string>)[status || ''] || status || '未知' }
function eventLabel(type?: string) { return ({ 'product.updated': '产品信息更新', 'deliverable.submitted': '登记交付物', 'deliverable.accepted': '交付物验收通过', 'deliverable.rejected': '交付物退回', 'release.created': '创建发布版本', 'runtime.registered': '登记运行实例', 'runtime.updated': '更新运行实例', 'runtime.health_synced': '同步运行健康', 'runtime.removed': '移除运行实例' } as Record<string, string>)[type || ''] || type || '产品活动' }
function formatTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false }) }

onMounted(loadProducts)
</script>

<style scoped>
.products-page { display: grid; gap: 18px; min-width: 0; }
.page-head, .section-head, .product-detail > header, .section-title, .head-actions, .detail-actions, .row-actions { display: flex; align-items: center; gap: 8px; }
.page-head, .section-head, .product-detail > header, .section-title { justify-content: space-between; }
.page-head h2, .page-head span, .section-head h3, .portfolio-leadership h3, .portfolio-group h4, .product-detail h3, .product-detail h4, .product-detail p { margin: 0; }
.page-head h2 { color: var(--text-primary); font-size: 18px; }
.page-head span, .section-head span, .portfolio-lead-copy span, .portfolio-flow small, .portfolio-group header span, .portfolio-product-card small, .chain-product span, .chain-product small, .product-detail header span, .detail-list small, .empty-inline, .timeline-list small { color: var(--text-secondary); font-size: 11px; }
.registry-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-top: 1px solid var(--line-color); border-bottom: 1px solid var(--line-color); }
.registry-metrics > div { display: grid; gap: 4px; padding: 10px 12px; border-right: 1px solid var(--line-color); }
.registry-metrics > div:last-child { border-right: 0; }
.registry-metrics span, .product-card-stats dt { color: var(--text-secondary); font-size: 11px; }
.registry-metrics strong { color: var(--text-primary); font-size: 20px; }
.dependency-band, .project-binding-band, .portfolio-leadership, .portfolio-modules, .featured-products, .evidence-panel, .roadmap-panel, .product-list, .product-detail { min-width: 0; padding: 14px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.portfolio-leadership { display: grid; grid-template-columns: minmax(260px, 0.9fr) minmax(0, 1.4fr); gap: 16px; align-items: stretch; }
.portfolio-lead-copy { display: grid; gap: 7px; align-content: center; }
.portfolio-lead-copy h3 { color: var(--text-primary); font-size: 18px; }
.portfolio-lead-copy p { margin: 0; color: var(--text-secondary); font-size: 12px; line-height: 1.6; }
.portfolio-flow { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.portfolio-flow > div { display: grid; gap: 5px; min-width: 0; padding: 10px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--view-color-faint); }
.portfolio-flow strong { color: var(--text-primary); font-size: 12px; }
.project-binding-band { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.project-binding-band > div:first-child { display: grid; gap: 3px; }
.project-binding-band span, .project-binding-band small { color: var(--text-secondary); font-size: 11px; }
.project-binding-band strong { color: var(--text-primary); font-size: 14px; }
.section-head { margin-bottom: 12px; }
.section-head h3, .product-detail h3 { color: var(--text-primary); font-size: 14px; }
.portfolio-group-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.portfolio-group { display: grid; gap: 10px; min-width: 0; padding: 12px; border: 1px solid var(--line-color); border-radius: 6px; background: color-mix(in srgb, var(--card-bg) 94%, var(--view-color-faint)); }
.portfolio-group > header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.portfolio-group h4 { color: var(--text-primary); font-size: 13px; }
.portfolio-product-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.portfolio-product-card { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 10px; align-items: center; min-width: 0; min-height: 76px; padding: 8px; border: 1px solid var(--line-color); border-radius: 6px; color: inherit; text-align: left; background: transparent; cursor: pointer; }
.portfolio-product-card:hover { border-color: var(--view-color-border); background: var(--view-color-faint); }
.portfolio-product-card strong, .portfolio-product-card small { display: block; overflow: hidden; text-overflow: ellipsis; }
.portfolio-product-card strong { color: var(--text-primary); font-size: 12px; white-space: nowrap; }
.portfolio-product-card small { display: -webkit-box; margin-top: 4px; line-height: 1.4; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.product-visual, .product-card-visual { display: grid; place-items: end start; overflow: hidden; border-radius: 5px; background-position: center; background-size: cover; color: #fff; }
.product-visual { width: 72px; height: 58px; }
.product-card-visual { min-height: 86px; padding: 10px; }
.product-visual span, .product-card-visual span { max-width: 100%; padding: 3px 5px; overflow: hidden; border-radius: 4px; background: rgb(0 0 0 / 42%); font-size: 11px; font-weight: 600; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
.featured-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.featured-card { display: grid; grid-template-rows: 170px minmax(0, 1fr); min-width: 0; overflow: hidden; border: 1px solid var(--line-color); border-radius: 6px; background: color-mix(in srgb, var(--card-bg) 92%, var(--view-color-faint)); }
.featured-visual { display: grid; place-items: end start; min-width: 0; padding: 12px; border: 0; background-position: center; background-size: cover; color: #fff; cursor: pointer; }
.featured-visual span { max-width: 100%; padding: 4px 7px; overflow: hidden; border-radius: 4px; background: rgb(0 0 0 / 48%); font-size: 12px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.featured-copy { display: grid; gap: 9px; min-width: 0; padding: 12px; }
.featured-copy > div:first-child { display: grid; gap: 4px; min-width: 0; }
.featured-copy span, .featured-copy p { color: var(--text-secondary); font-size: 11px; }
.featured-copy h4 { margin: 0; overflow: hidden; color: var(--text-primary); font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.featured-copy p { display: -webkit-box; min-height: 49px; margin: 0; overflow: hidden; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.featured-tags { display: flex; flex-wrap: wrap; gap: 6px; min-height: 24px; }
.featured-card footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: auto; }
.evidence-roadmap { display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, 0.72fr); gap: 14px; align-items: start; }
.evidence-product-list { display: grid; gap: 8px; }
.evidence-product-list button { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-width: 0; padding: 9px 10px; border: 1px solid var(--line-color); border-radius: 6px; color: inherit; text-align: left; background: transparent; cursor: pointer; }
.evidence-product-list button:hover { border-color: var(--view-color-border); background: var(--view-color-faint); }
.evidence-product-list strong, .evidence-product-list small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.evidence-product-list strong { color: var(--text-primary); font-size: 12px; }
.evidence-product-list small { flex: none; color: var(--text-secondary); font-size: 11px; }
.roadmap-list { display: grid; gap: 0; margin: 0; padding: 0; list-style: none; }
.roadmap-list article { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 8px; padding: 9px 0; border-bottom: 1px solid var(--line-color); }
.roadmap-list article:last-child { border-bottom: 0; }
.roadmap-list article::before { width: 8px; height: 8px; margin: 7px auto 0; border: 1px solid var(--view-color-border); border-radius: 50%; background: var(--view-color-faint); content: ""; }
.roadmap-list strong, .roadmap-list small { display: block; min-width: 0; }
.roadmap-list strong { color: var(--text-primary); font-size: 12px; }
.roadmap-list small { margin-top: 3px; color: var(--text-secondary); font-size: 11px; line-height: 1.45; }
.core-chain { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr); gap: 10px; align-items: center; }
.chain-product { display: grid; gap: 4px; min-width: 0; padding: 8px 10px; border: 0; border-left: 2px solid var(--view-color-border); color: inherit; text-align: left; background: transparent; cursor: pointer; }
.chain-product:hover { background: var(--view-color-faint); }
.chain-product strong, .chain-product small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chain-product strong { color: var(--text-primary); font-size: 13px; }
.chain-arrow { color: var(--text-secondary); }
.registry-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 390px); gap: 14px; align-items: start; }
.product-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.product-card { display: grid; min-height: 224px; gap: 12px; padding: 14px; border: 1px solid var(--line-color); border-radius: 6px; color: inherit; text-align: left; background: color-mix(in srgb, var(--card-bg) 92%, var(--view-color-faint)); box-shadow: 0 7px 20px rgb(0 0 0 / 8%); cursor: pointer; transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease; }
.product-card:hover { transform: translateY(-2px); border-color: var(--view-color-border); box-shadow: 0 12px 24px rgb(0 0 0 / 13%); }
.product-card.selected { border-color: var(--view-color-border); box-shadow: inset 0 0 0 1px var(--view-color-border), 0 12px 24px rgb(0 0 0 / 13%); }
.product-card > header, .product-card > footer, .product-card-stats { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.product-kind { padding-left: 8px; border-left: 2px solid var(--view-color-border); color: var(--text-secondary); font-size: 11px; }
.product-card-title { display: grid; gap: 5px; }
.product-card-title strong { color: var(--text-primary); font-size: 15px; }
.product-card-title small, .product-card p, .product-card footer { color: var(--text-secondary); font-size: 11px; }
.product-card p { min-height: 34px; margin: 0; line-height: 1.5; }
.product-card-stats { margin: auto 0 0; padding: 9px 0; border-top: 1px solid var(--line-color); border-bottom: 1px solid var(--line-color); }
.product-card-stats > div { display: grid; gap: 4px; }
.product-card-stats dd { margin: 0; color: var(--text-primary); font-size: 16px; font-weight: 600; }
.product-card > footer { align-items: flex-start; }
.product-card > footer > span:last-child { max-width: 55%; overflow: hidden; text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.product-detail { display: grid; gap: 16px; position: sticky; top: 14px; max-height: calc(100vh - 124px); overflow: auto; }
.product-detail p { color: var(--text-secondary); font-size: 12px; line-height: 1.6; }
.product-detail section { display: grid; gap: 8px; padding-top: 12px; border-top: 1px solid var(--line-color); }
.product-detail h4 { color: var(--text-primary); font-size: 12px; }
.product-facts { display: grid; margin: 0; }
.product-facts > div { display: grid; grid-template-columns: 76px minmax(0, 1fr); gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--line-color); font-size: 11px; }
.product-facts dt { color: var(--text-secondary); }
.product-facts dd { min-width: 0; margin: 0; overflow-wrap: anywhere; color: var(--text-primary); }
.tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
.detail-list, .timeline-list { display: grid; }
.detail-list > div, .timeline-list > div { min-width: 0; padding: 7px 0; border-bottom: 1px solid var(--line-color); }
.detail-list > div:last-child, .timeline-list > div:last-child { border-bottom: 0; }
.detail-list strong, .timeline-list strong { display: block; overflow: hidden; color: var(--text-primary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.detail-list small { display: block; margin-top: 3px; line-height: 1.45; overflow-wrap: anywhere; }
.linked-row, .delivery-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.linked-row > button { min-width: 0; padding: 0; border: 0; color: inherit; text-align: left; background: transparent; cursor: pointer; }
.row-actions { flex: none; }
.timeline-list > div { display: flex; justify-content: space-between; gap: 8px; }
.timeline-list small { flex: none; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 12px; }
.dialog-form :deep(.el-select), .dialog-form :deep(.el-input-number) { width: 100%; }
.dialog-spacer { flex: 1; }
@media (max-width: 1100px) { .portfolio-leadership, .portfolio-group-grid, .featured-grid, .evidence-roadmap, .registry-layout { grid-template-columns: 1fr; } .portfolio-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); } .product-detail { position: static; max-height: none; } }
@media (max-width: 680px) { .page-head, .project-binding-band { align-items: flex-start; flex-direction: column; } .registry-metrics, .portfolio-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); } .registry-metrics > div:nth-child(2) { border-right: 0; } .registry-metrics > div:nth-child(-n + 2) { border-bottom: 1px solid var(--line-color); } .portfolio-product-list, .product-grid, .form-grid { grid-template-columns: 1fr; } .core-chain { grid-template-columns: 1fr; } .chain-arrow { transform: rotate(90deg); text-align: center; } .head-actions { flex-wrap: wrap; } .featured-card { grid-template-rows: 150px minmax(0, 1fr); } .evidence-product-list button { display: grid; } .evidence-product-list small { flex: auto; } }
</style>
