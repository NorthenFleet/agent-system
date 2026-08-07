<template>
  <div class="writing-page" v-loading="loading">
    <header class="writing-head">
      <div>
        <span class="eyebrow">文档撰写</span>
        <div class="title-line">
          <h2>{{ workspace?.project.name || documentCollection?.project.name || '文档工作台' }}</h2>
          <el-tag v-if="workspace?.manifest.edition" effect="plain" size="small">{{ currentEditionLabel }}</el-tag>
        </div>
        <p>{{ workspace?.project.description || documentCollection?.project.description || '研究组织、全文写作、证据管理与最终交付' }}</p>
      </div>
      <div class="head-actions">
        <el-button type="primary" :icon="Plus" @click="openProjectDialog()">新建项目</el-button>
        <el-tooltip content="刷新文档工作台" placement="bottom">
          <el-button :icon="Refresh" circle @click="refreshAll" />
        </el-tooltip>
      </div>
    </header>

    <section class="document-manager">
      <header class="manager-head">
        <div>
          <span class="eyebrow">文档项目</span>
          <h3>{{ projects.length }} 个撰写项目</h3>
        </div>
        <el-input v-model="projectSearch" :prefix-icon="Search" clearable placeholder="搜索文档名称、类型或负责人" />
      </header>
      <div v-if="filteredProjects.length" class="document-project-list">
        <article
          v-for="project in filteredProjects"
          :key="project.id"
          class="document-project-card"
          :class="{ active: selectedProjectId === project.id, archived: project.status === 'archived' }"
          @click="selectProject(project.id)"
        >
          <div class="project-card-main">
            <span class="document-icon"><el-icon><Document /></el-icon></span>
            <div>
              <div class="project-name-line">
                <strong>{{ project.name }}</strong>
                <el-tag size="small" :type="projectStatusType(project.status)" effect="plain">
                  {{ projectStatusLabel(project.status) }}
                </el-tag>
              </div>
              <p>{{ project.description || '暂无文档说明' }}</p>
            </div>
          </div>
          <div class="project-card-meta">
            <span>{{ project.document_spec?.document_type || '文档' }}</span>
            <span>{{ project.document_spec?.chapters?.length || 0 }} 个计划章节</span>
            <span>{{ project.owner_agent || '未分配' }}</span>
          </div>
          <el-progress :percentage="Math.round(project.progress || 0)" :stroke-width="4" :show-text="false" />
          <div class="project-card-actions">
            <el-tooltip content="编辑文档信息">
              <el-button circle text :icon="EditPen" aria-label="编辑文档信息" @click.stop="openProjectDialog(project)" />
            </el-tooltip>
            <el-tooltip :content="project.status === 'archived' ? '恢复文档' : '归档文档'">
              <el-button circle text :icon="FolderOpened" :aria-label="project.status === 'archived' ? '恢复文档' : '归档文档'" @click.stop="toggleProjectArchive(project)" />
            </el-tooltip>
            <el-tooltip v-if="project.status === 'archived'" content="永久删除文档项目">
              <el-button circle text type="danger" :icon="Delete" aria-label="永久删除文档项目" @click.stop="removeProject(project)" />
            </el-tooltip>
          </div>
        </article>
      </div>
      <el-empty v-else description="暂无匹配的文档项目" :image-size="68" />
    </section>

    <section v-if="selectedProjectId" class="project-document-library">
      <section v-if="isCourseProject" class="course-production-panel">
        <header>
          <div>
            <span class="eyebrow">课程生产基线</span>
            <h3>{{ productionStatus?.course_profile.canonical_title || '水面舰艇作战软件与兵棋推演' }}</h3>
          </div>
          <div class="course-panel-actions">
            <el-button
              size="small"
              :icon="Tickets"
              :loading="syncingCourseWorkPlan"
              @click="syncCourseWorkPlan"
            >
              同步课程任务
            </el-button>
            <el-tag
              :type="productionStatus?.summary.can_export ? 'success' : 'warning'"
              effect="plain"
            >
              {{ productionStatus?.summary.can_export ? '可正式交付' : '生产中' }}
            </el-tag>
          </div>
        </header>
        <div class="course-baseline-metrics">
          <div><span>总学时</span><strong>{{ productionStatus?.course_profile.total_hours || 20 }}</strong></div>
          <div><span>课程单元</span><strong>{{ productionStatus?.course_profile.units?.length || 10 }} 讲</strong></div>
          <div><span>理论 / 实作 / 考核</span><strong>{{ productionStatus?.course_profile.theory_hours || 4 }} / {{ productionStatus?.course_profile.practice_hours || 14 }} / {{ productionStatus?.course_profile.assessment_hours || 2 }}</strong></div>
          <div><span>必需产品</span><strong>{{ productionStatus?.summary.ready || 0 }} / {{ productionStatus?.summary.required || 16 }}</strong></div>
          <div><span>生产任务</span><strong>{{ productionStatus?.work_plan?.summary.tracked || 0 }} / {{ productionStatus?.work_plan?.summary.required || 6 }}</strong></div>
          <div><span>执行要点</span><strong>{{ productionStatus?.work_plan?.summary.completed_points || 0 }} / {{ productionStatus?.work_plan?.summary.points || 0 }}</strong></div>
        </div>
        <div class="course-iteration-bar">
          <div class="course-iteration-status">
            <span><small>当前轮次</small><strong>{{ productionStatus?.work_plan?.execution?.current_iteration || 0 }}</strong></span>
            <span><small>可执行</small><strong>{{ productionStatus?.work_plan?.execution?.eligible_points || 0 }}</strong></span>
            <span><small>排队 / 执行</small><strong>{{ productionStatus?.work_plan?.execution?.queued_points || 0 }} / {{ productionStatus?.work_plan?.execution?.active_points || 0 }}</strong></span>
            <span><small>待评审 / 阻塞</small><strong>{{ productionStatus?.work_plan?.execution?.review_points || 0 }} / {{ productionStatus?.work_plan?.execution?.blocked_points || 0 }}</strong></span>
          </div>
          <div class="course-iteration-controls">
            <label>
              <span>迭代轮次</span>
              <el-input-number v-model="courseIterationRounds" :min="1" :max="10" controls-position="right" />
            </label>
            <label>
              <span>并行数</span>
              <el-input-number v-model="courseIterationParallelism" :min="1" :max="4" controls-position="right" />
            </label>
            <el-button
              type="primary"
              :icon="VideoPlay"
              :loading="runningCourseIteration"
              :disabled="!(productionStatus?.work_plan?.execution?.eligible_points || 0)"
              @click="executeCourseIteration"
            >
              执行下一批
            </el-button>
          </div>
        </div>
        <div v-if="productionStatus?.work_plan?.workstreams?.length" class="course-workstream-table">
          <div
            v-for="workstream in productionStatus.work_plan.workstreams"
            :key="workstream.key"
            class="course-workstream-row"
          >
            <div>
              <strong>{{ workstream.title }}</strong>
              <small>{{ courseAgentName(workstream.assignee_agent) }}</small>
            </div>
            <el-progress
              :percentage="Math.round(workstream.progress || 0)"
              :stroke-width="5"
              :show-text="false"
            />
            <span>{{ workstream.completed_points }} / {{ workstream.points }} 要点</span>
            <el-tag
              size="small"
              :type="workstream.dependency_ready ? courseWorkStatusType(workstream.status) : 'info'"
              effect="plain"
            >
              {{ workstream.dependency_ready ? courseWorkStatusLabel(workstream.status) : '等待依赖' }}
            </el-tag>
          </div>
        </div>
        <section v-if="courseAttentionPoints.length" class="course-attention-list">
          <header>
            <strong>当前执行与评审</strong>
            <small>{{ courseAttentionPoints.length }} 个要点</small>
          </header>
          <div v-for="point in courseAttentionPoints" :key="point.id" class="course-attention-row">
            <div>
              <strong>{{ point.title }}</strong>
              <small>第 {{ point.iteration || '-' }} 轮 · {{ courseAgentName(point.assigned_agent) }} · {{ point.task_title }}</small>
            </div>
            <el-tag size="small" :type="courseWorkStatusType(point.status)" effect="plain">
              {{ courseWorkStatusLabel(point.status) }}
            </el-tag>
            <div class="course-review-actions">
              <template v-if="point.status === 'review'">
                <el-button
                  size="small"
                  type="success"
                  plain
                  :loading="reviewingCoursePointId === point.id"
                  @click="reviewCourseExecutionPoint(point, 'approve')"
                >
                  通过
                </el-button>
                <el-button
                  size="small"
                  type="warning"
                  plain
                  :disabled="Boolean(reviewingCoursePointId)"
                  @click="reviewCourseExecutionPoint(point, 'reject')"
                >
                  退回
                </el-button>
              </template>
              <el-button
                v-else-if="point.status === 'blocked'"
                size="small"
                plain
                :loading="reviewingCoursePointId === point.id"
                @click="reviewCourseExecutionPoint(point, 'retry')"
              >
                重新排队
              </el-button>
            </div>
          </div>
        </section>
        <div v-if="productionStatus?.blockers.length" class="course-blocker-preview">
          <span>{{ productionStatus.blockers[0].message }}</span>
          <el-button text type="warning" @click="productionDialogVisible = true">
            查看全部 {{ productionStatus.blockers.length }} 项
          </el-button>
        </div>
      </section>
      <header class="document-library-head">
        <div>
          <span class="eyebrow">项目内文档</span>
          <h3>{{ formalDocuments.length }} 册正式文档 · {{ internalDataSources.length }} 项内部数据源</h3>
        </div>
        <div class="document-library-actions">
          <el-switch v-model="showArchivedDocuments" active-text="显示归档" @change="loadDocuments" />
          <el-button
            v-if="isCourseProject"
            :icon="Refresh"
            :loading="applyingCourseTemplate"
            @click="applyCourseTemplate"
          >
            应用20学时模板
          </el-button>
          <el-upload
            v-if="isCourseProject"
            accept=".docx"
            :auto-upload="false"
            :show-file-list="false"
            :disabled="importingDocx"
            :on-change="importCourseDocx"
          >
            <el-button :icon="UploadFilled" :loading="importingDocx">导入Word材料</el-button>
          </el-upload>
          <el-button
            :icon="FolderOpened"
            :loading="exportingPackage"
            :disabled="!formalDocuments.length"
            @click="exportFormalPackage"
          >
            导出正式交付包
          </el-button>
          <el-button :icon="Plus" type="primary" @click="openDocumentDialog()">新增文档</el-button>
        </div>
      </header>
      <div v-if="documentCollection?.documents.length" class="document-groups">
        <section class="document-group formal-documents">
          <header>
            <div><strong>正式文档</strong><small>Word、PDF与PPT统一交付</small></div>
            <el-tag type="success" effect="plain">{{ formalDocuments.length }} 册</el-tag>
          </header>
          <div class="project-document-list">
            <article
              v-for="documentItem in formalDocuments"
              :key="documentItem.id"
              :class="['project-document-card', { active: selectedDocumentId === documentItem.id, archived: documentItem.status === 'archived' }]"
              @click="selectDocument(documentItem.id)"
            >
              <span class="document-type-icon"><el-icon><component :is="documentKindIcon(documentItem.kind)" /></el-icon></span>
              <div class="document-card-body">
                <div>
                  <strong>{{ documentItem.title }}</strong>
                  <el-tag v-if="documentItem.is_primary" size="small" type="success" effect="plain">主文档</el-tag>
                  <el-tag v-if="documentItem.status === 'archived'" size="small" type="info" effect="plain">已归档</el-tag>
                  <el-tag v-if="documentItem.product_type" size="small" effect="plain">
                    {{ courseProductLabel(documentItem.product_type) }}
                  </el-tag>
                  <el-tag size="small" :type="publicationTagType(documentItem.publication_status)" effect="plain">
                    {{ publicationLabel(documentItem.publication_status) }}
                  </el-tag>
                  <el-tag
                    v-if="documentItem.structure_binding"
                    size="small"
                    :type="structureBindingTagType(documentItem.structure_binding.status)"
                    effect="plain"
                  >
                    {{ structureBindingLabel(documentItem.structure_binding.status) }}
                  </el-tag>
                  <el-tag
                    v-if="richTextDeliveryState(documentItem) === 'stale'"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    交付待同步
                  </el-tag>
                </div>
                <small>{{ documentOutputSummary(documentItem) }}</small>
              </div>
              <div class="document-card-actions">
                <el-button circle text :icon="ArrowUp" :disabled="documentOrderIndex(documentItem) === 0" @click.stop="moveDocument(documentItem, -1)" />
                <el-button circle text :icon="ArrowDown" :disabled="documentOrderIndex(documentItem) === documentOrderCount - 1" @click.stop="moveDocument(documentItem, 1)" />
                <el-button circle text :icon="EditPen" @click.stop="openDocumentDialog(documentItem)" />
                <el-button circle text :disabled="documentItem.is_primary" :icon="FolderOpened" @click.stop="toggleDocumentArchive(documentItem)" />
                <el-button v-if="documentItem.status === 'archived' && !documentItem.is_primary" circle text type="danger" :icon="Delete" @click.stop="removeDocument(documentItem)" />
              </div>
            </article>
            <el-empty v-if="!formalDocuments.length" description="暂无正式文档" :image-size="52" />
          </div>
        </section>

        <section class="document-group internal-documents">
          <header>
            <div><strong>内部数据源</strong><small>仅供数据管理与计算，不进入交付包</small></div>
            <el-tag type="info" effect="plain">{{ internalDataSources.length }} 项</el-tag>
          </header>
          <div class="project-document-list">
            <article
              v-for="documentItem in internalDataSources"
              :key="documentItem.id"
              :class="['project-document-card', 'internal', { active: selectedDocumentId === documentItem.id, archived: documentItem.status === 'archived' }]"
              @click="selectDocument(documentItem.id)"
            >
              <span class="document-type-icon"><el-icon><component :is="documentKindIcon(documentItem.kind)" /></el-icon></span>
              <div class="document-card-body">
                <div>
                  <strong>{{ documentItem.title }}</strong>
                  <el-tag size="small" type="info" effect="plain">内部</el-tag>
                  <el-tag v-if="documentItem.status === 'archived'" size="small" type="info" effect="plain">已归档</el-tag>
                </div>
                <small>{{ documentKindLabel(documentItem.kind) }} · {{ documentVersionLabel(documentItem) }} · {{ documentStatLabel(documentItem) }}</small>
              </div>
              <div class="document-card-actions">
                <el-button circle text :icon="ArrowUp" :disabled="documentOrderIndex(documentItem) === 0" @click.stop="moveDocument(documentItem, -1)" />
                <el-button circle text :icon="ArrowDown" :disabled="documentOrderIndex(documentItem) === documentOrderCount - 1" @click.stop="moveDocument(documentItem, 1)" />
                <el-button circle text :icon="EditPen" @click.stop="openDocumentDialog(documentItem)" />
                <el-button circle text :icon="FolderOpened" @click.stop="toggleDocumentArchive(documentItem)" />
                <el-button v-if="documentItem.status === 'archived'" circle text type="danger" :icon="Delete" @click.stop="removeDocument(documentItem)" />
              </div>
            </article>
            <el-empty v-if="!internalDataSources.length" description="暂无内部数据源" :image-size="52" />
          </div>
        </section>
      </div>
      <el-empty v-else description="项目内暂无文档" :image-size="60" />
    </section>

    <el-tabs
      v-if="documentCollection?.documents.length"
      v-model="studioMode"
      class="content-studio-tabs"
      @tab-change="handleStudioModeChange"
    >
      <el-tab-pane label="文档撰写" name="document" :disabled="!richTextDocuments.length" />
      <el-tab-pane label="PPT 制作" name="presentation" :disabled="!presentationDocuments.length" />
      <el-tab-pane label="联动工作台" name="linked" :disabled="!richTextDocuments.length || !presentationDocuments.length" />
    </el-tabs>

    <WritingLinkedWorkspace
      v-if="studioMode === 'linked' && currentDocument?.kind === 'rich_text' && workspace"
      :project-id="selectedProjectId"
      :source-document="currentDocument"
      :presentation-document="linkedPresentationDocument"
      :section-id="selectedSectionId"
      :outline="workspace.directory"
      :selected-node-id="selectedDirectoryNodeId"
      :presentation-slide="presentationInitialSlide"
      @select-outline="selectDirectoryNode"
      @navigate-to-thesis="navigateFromLinkedPresentation"
      @slide-changed="presentationInitialSlide = $event"
      @changed="handleLinkedWorkspaceChanged"
    />

    <template v-else-if="currentDocument?.kind === 'rich_text'">
    <section v-if="workspace" class="status-strip">
      <div><span>当前版本</span><strong class="edition-value">{{ currentEditionLabel }} · {{ currentContentVersionLabel }}</strong></div>
      <div><span>章节</span><strong>{{ workspace.stats.chapter_count }}</strong></div>
      <div><span>正文规模</span><strong>{{ formatNumber(workspace.stats.word_count) }}</strong></div>
      <div><span>图表</span><strong>{{ workspace.stats.image_count }}</strong></div>
      <div><span>正式文献</span><strong>{{ workspace.reference_summary.formal }}</strong></div>
      <div><span>技术完整度</span><strong :class="qualityClass">{{ workspace.quality.score }}</strong></div>
    </section>

    <el-tabs v-model="activeView" class="workspace-tabs" @tab-change="handleViewChange">
      <el-tab-pane label="研究总览" name="overview" />
      <el-tab-pane label="文档撰写" name="reader" />
      <el-tab-pane label="概念与论证" name="graph" />
      <el-tab-pane label="参考文献" name="references" />
      <el-tab-pane label="排版与交付" name="delivery" />
    </el-tabs>

    <template v-if="workspace">
      <main v-if="activeView === 'overview'" class="overview-view">
        <section class="research-brief">
          <header class="section-title">
            <div><span>研究主线</span><h3>{{ overviewProfileTitle }}</h3></div>
            <el-tag effect="plain">{{ workspace.project.document_spec?.document_type || '博士论文' }}</el-tag>
          </header>
          <div class="brief-grid">
            <div>
              <span>写作目标</span>
              <p>{{ workspace.project.document_spec?.writing_goal || '围绕海上无人集群智能协同任务规划形成完整理论、模型、方法与验证体系。' }}</p>
            </div>
            <div>
              <span>目标读者</span>
              <p>{{ workspace.project.document_spec?.target_audience || '导师、评审专家和相关研究人员' }}</p>
            </div>
            <div>
              <span>当前工作稿</span>
              <p>{{ workspace.manifest.working_markdown }}</p>
            </div>
            <div>
              <span>最终输出</span>
              <p>{{ workspace.project.document_spec?.output_format || 'Markdown / Word / PDF' }}</p>
            </div>
          </div>
        </section>

        <section v-if="isThesisDocument" class="version-evolution">
          <header class="section-title">
            <div><span>版本演进</span><h3>论文版本链</h3></div>
            <el-tag effect="plain">{{ publicationEditionLabel }}交付目标</el-tag>
          </header>
          <div class="version-timeline">
            <article v-for="stage in versionStages" :key="stage.key" :class="['version-stage', stage.state]">
              <span>{{ stage.label }}</span>
              <strong>{{ stage.title }}</strong>
              <p>{{ stage.description }}</p>
              <small>{{ stage.meta }}</small>
            </article>
          </div>
        </section>

        <div
          class="structure-comparison"
          :class="{ 'is-single': !currentStructure }"
        >
          <section v-if="currentStructure" class="target-structure">
            <header class="section-title target-structure__head">
              <div>
                <span>当前目录结构</span>
                <h3>{{ publicationStructureTitle }}</h3>
              </div>
              <div class="target-structure__badges">
                <el-tag type="success" effect="plain">{{ currentEditionLabel }} {{ currentStructure.chapter_count }} 章</el-tag>
              </div>
            </header>
            <DocumentStructureStatus
              :sync="workspace.structure_sync"
              :target-label="publicationEditionLabel"
            />
            <div class="target-structure__meta">
              <span>{{ publicationStructureVersion }}</span>
              <span>{{ currentStructure.heading_count || 0 }} 个目录项</span>
              <span>{{ currentStructure.source_path || workspace.manifest.working_markdown }}</span>
            </div>
            <div class="target-chapter-list">
              <details
                v-for="chapter in currentStructure.chapters"
                :key="chapter.number"
                class="target-chapter"
              >
                <summary>
                  <strong>{{ chapter.title }}</strong>
                  <small>{{ chapter.outline.length }} 个节项</small>
                </summary>
                <ol>
                  <li
                    v-for="item in chapter.outline"
                    :key="`${chapter.number}-${item.title}`"
                    :class="`outline-level-${item.level}`"
                  >{{ item.title }}</li>
                </ol>
              </details>
            </div>
          </section>

          <div class="chapter-progress">
            <header class="section-title"><div><span>写作结构</span><h3>章节进展</h3></div></header>
            <p class="comparison-hint">与左侧当前目录逐章对照，点击章节进入正文。</p>
            <button
              v-for="section in chapterSections"
              :key="section.id"
              type="button"
              class="chapter-row"
              @click="openSection(section)"
            >
              <div><strong>{{ section.title }}</strong><small>{{ section.outline.length }} 节 · {{ formatNumber(section.word_count) }} 字符</small></div>
              <el-tag size="small" :type="sectionDeliveryStatus(section).type" effect="plain">
                {{ sectionDeliveryStatus(section).label }}
              </el-tag>
            </button>
          </div>
        </div>

        <DocumentEvaluationPanel
          :profile="evaluationProfile"
          :report="evaluationReport"
          :linked-summary="linkedEvaluationSummary"
          :profiles="evaluationProfiles"
          :busy="evaluationBusy"
          @run="runEvaluation"
          @confirm="confirmEvaluation"
          @save-profile="saveEvaluationProfile"
        />

        <aside class="quality-panel">
          <header class="section-title">
            <div><span>自动技术检查</span><h3>技术完整度</h3></div>
            <strong class="quality-score" :class="qualityClass">{{ workspace.quality.score }}</strong>
          </header>
          <div class="quality-facts">
            <div><span>阻断问题</span><strong>{{ workspace.quality.blockers }}</strong></div>
            <div><span>警告</span><strong>{{ workspace.quality.warnings }}</strong></div>
            <div><span>缺失图片</span><strong>{{ workspace.quality.missing_assets }}</strong></div>
            <div><span>未引用文献</span><strong>{{ workspace.quality.uncited_references }}</strong></div>
          </div>
          <el-button text type="primary" @click="activeView = 'delivery'; loadDelivery()">查看完整技术报告</el-button>
        </aside>
      </main>

      <main v-else-if="activeView === 'reader'" class="reader-view" :class="{ 'is-collaboration': readerMode === 'section' }">
        <section v-if="readerMode === 'section'" class="collaboration-reader">
          <header class="collaboration-reader__toolbar">
            <el-segmented v-model="readerMode" :options="readerModes" size="small" @change="changeReaderMode" />
            <div class="collaboration-reader__context">
              <el-button
                v-for="item in linkedPresentationSlides"
                :key="`${item.documentId}-${item.slide}`"
                size="small"
                text
                @click="openPresentationSlide(item.documentId, item.slide)"
              >当前章节关联 PPT · 第{{ item.slide }}页</el-button>
              <span>章节修改会自动保存；AI 修改不同段落时自动合并，同段变化转为待审建议。</span>
            </div>
          </header>
          <el-skeleton v-if="sectionLoading || !currentSection" :rows="14" animated />
          <CollaborativeWritingEditor
            v-else
            ref="collaborationEditor"
            :key="`${selectedProjectId}-${selectedDocumentId}-${selectedSectionId}`"
            :project-id="selectedProjectId"
            :document-id="selectedDocumentId"
            :document-title="currentDocument?.title"
            :section-id="selectedSectionId"
            :outline="workspace.directory"
            :selected-node-id="selectedDirectoryNodeId"
            @select-outline="selectDirectoryNode"
          />
        </section>

        <DocumentOutlineTree
          v-else
          :nodes="workspace.directory"
          :project-id="selectedProjectId"
          :document-id="selectedDocumentId"
          selected-node-id=""
          @select="selectDirectoryNode"
        />

        <section v-if="readerMode === 'full'" class="document-pane">
          <header class="document-toolbar">
            <el-segmented v-model="readerMode" :options="readerModes" size="small" @change="changeReaderMode" />
          </header>
          <el-skeleton v-if="sectionLoading" :rows="12" animated />
          <article ref="documentBody" v-else class="markdown-body" v-html="renderedDocument" />
        </section>

        <aside v-if="readerMode === 'full'" class="inspector-pane">
          <span class="eyebrow">全文阅读</span>
          <h3>完整工作正文</h3>
          <p>全文仅在需要连续审阅时加载。日常写作建议按章节进行，以保持目录、引用和版本边界清晰。</p>
        </aside>
      </main>

      <main v-else-if="activeView === 'graph'" class="graph-view">
        <header class="graph-toolbar">
          <div><span class="eyebrow">知识库概念骨架</span><h3>概念、章节与论证关系</h3></div>
          <el-segmented v-model="graphMode" :options="graphModes" size="small" @change="renderGraph" />
        </header>
        <section class="graph-metrics">
          <div><span>章节</span><strong>{{ graphData?.summary.sections || 0 }}</strong></div>
          <div><span>匹配概念</span><strong>{{ graphData?.summary.concepts || 0 }}</strong></div>
          <div><span>论点</span><strong>{{ graphData?.summary.claims || 0 }}</strong></div>
          <div><span>关系</span><strong>{{ graphData?.summary.relations || 0 }}</strong></div>
        </section>
        <div ref="graphElement" class="graph-canvas" />
        <aside v-if="selectedGraphNode" class="graph-selection">
          <span>{{ graphNodeTypeLabel(selectedGraphNode.type) }}</span>
          <strong>{{ selectedGraphNode.name }}</strong>
          <p v-if="selectedGraphNode.detail">{{ selectedGraphNode.detail }}</p>
        </aside>
      </main>

      <main v-else-if="activeView === 'references'" class="references-view">
        <header class="reference-toolbar">
          <div><span class="eyebrow">证据链</span><h3>知识资料与正式论文引用</h3></div>
          <div class="reference-controls">
            <el-segmented v-model="referenceStatus" :options="referenceStatusOptions" size="small" />
            <el-input v-model="referenceSearch" :prefix-icon="Search" placeholder="检索文献" clearable />
          </div>
        </header>
        <section class="reference-audit-strip">
          <div><span>正式文献</span><strong>{{ references?.summary.formal || 0 }}</strong></div>
          <div><span>已引用</span><strong>{{ references?.summary.cited || 0 }}</strong></div>
          <div><span>未检出</span><strong class="quality-warning">{{ references?.summary.uncited || 0 }}</strong></div>
          <div><span>正文引用</span><strong>{{ references?.summary.in_text_citations || 0 }}</strong></div>
          <div><span>覆盖章节</span><strong>{{ references?.summary.sections_with_citations || 0 }}</strong></div>
        </section>
        <section class="citation-coverage">
          <header><div><span>章节审计</span><h3>引用覆盖</h3></div><small>点击章节可返回正文核验</small></header>
          <div class="coverage-list">
            <button v-for="section in references?.section_coverage || []" :key="section.section_id" type="button" @click="openReferenceLocation(section)">
              <strong>{{ section.title }}</strong>
              <span>{{ section.unique_references }} 篇 · {{ section.citation_occurrences }} 次</span>
            </button>
          </div>
        </section>
        <div class="reference-columns">
          <section>
            <header><div><span>研究资料</span><h3>知识库资料</h3></div><el-tag effect="plain">{{ references?.knowledge.length || 0 }}</el-tag></header>
            <div v-if="filteredKnowledgeReferences.length" class="knowledge-reference-list">
              <article v-for="reference in filteredKnowledgeReferences" :key="reference.id">
                <strong>{{ reference.title || reference.text }}</strong>
                <small>{{ reference.note || reference.source_type || '知识库上下文' }}</small>
              </article>
            </div>
            <el-empty v-else description="暂无匹配的知识库资料" :image-size="64" />
          </section>
          <section>
            <header><div><span>文末书目</span><h3>正式参考文献</h3></div><el-tag type="success" effect="plain">{{ references?.formal.length || 0 }}</el-tag></header>
            <div class="formal-reference-list">
              <article v-for="reference in filteredFormalReferences" :key="reference.id">
                <span>[{{ reference.number }}]</span>
                <div>
                  <strong>{{ reference.text }}</strong>
                  <small>{{ reference.year || '年份待核验' }} · 正文出现 {{ reference.usage_count || 0 }} 次 · 覆盖 {{ reference.section_count || 0 }} 个章节</small>
                  <div v-if="reference.locations?.length" class="reference-locations">
                    <button v-for="location in reference.locations" :key="`${reference.id}-${location.section_id}`" type="button" @click="openReferenceLocation(location)">
                      {{ location.title }} · {{ location.count }} 次
                    </button>
                  </div>
                  <small v-else class="uncited-note">需人工核验：确认保留、删除或在适当论述处补引</small>
                </div>
                <el-tag size="small" :type="reference.usage_count ? 'success' : 'warning'" effect="plain">
                  {{ reference.usage_count ? '已引用' : '未检出' }}
                </el-tag>
              </article>
            </div>
          </section>
        </div>
      </main>

      <main v-else class="delivery-view">
        <section class="delivery-main">
          <header class="section-title"><div><span>格式权威</span><h3>Word 与 PDF 交付</h3></div></header>
          <div class="source-grid">
            <div>
              <span>{{ layoutState?.binding.latest_delivery?.docx_path ? '当前交付 Word' : `${publicationEditionLabel} Word` }}</span>
              <strong>{{ layoutState?.binding.latest_delivery?.docx_path || workspace.manifest.source_word || '未登记' }}</strong>
              <el-button
                text
                :disabled="!layoutState?.binding.latest_delivery?.docx_path && !workspace.manifest.source_word"
                @click="layoutState?.binding.latest_delivery?.docx_path ? downloadLayoutDelivery('docx') : downloadSourceWord()"
              >
                {{ layoutState?.binding.latest_delivery?.docx_path ? '下载交付稿' : '下载原文' }}
              </el-button>
            </div>
            <div>
              <span>{{ currentEditionLabel }} Markdown 工作稿</span>
              <strong>{{ workspace.manifest.working_markdown }}</strong>
              <el-tag effect="plain">{{ currentContentVersionLabel }}</el-tag>
              <el-tag type="info" effect="plain">协同修订 r{{ workspace.manifest.version }}</el-tag>
            </div>
          </div>
          <DocumentLayoutPanel
            :layout="layoutState"
            :busy="exporting"
            :saving="layoutSaving"
            @save="saveLayout"
            @export="exportDocument"
            @preview-sample="previewLayoutSample"
            @download-delivery="downloadLayoutDelivery"
          />
          <el-alert :title="deliveryGuidance" type="info" :closable="false" show-icon />
        </section>

        <aside class="delivery-side">
          <section>
            <header class="section-title"><div><span>版本</span><h3>修改历史</h3></div></header>
            <div class="version-list">
              <div v-for="version in versions" :key="version.name">
                <strong>{{ version.name }}</strong><small>{{ formatDate(version.created_at) }} · {{ formatFileSize(version.size_bytes) }}</small>
              </div>
            </div>
          </section>
          <section>
            <header class="section-title"><div><span>检查</span><h3>质量报告</h3></div></header>
            <div class="issue-list">
              <div v-for="issue in qualityReport?.issues || []" :key="`${issue.type}-${issue.message}`">
                <el-tag size="small" :type="issue.severity === 'blocker' ? 'danger' : 'warning'" effect="plain">
                  {{ issue.severity === 'blocker' ? '阻断' : '警告' }}
                </el-tag>
                <span>{{ issue.message }}</span>
              </div>
              <span v-if="!qualityReport?.issues.length" class="muted">暂无质量问题</span>
            </div>
          </section>
        </aside>
      </main>
    </template>
    </template>

    <WorkbookWorkspace
      v-else-if="studioMode === 'workbook' && currentDocument?.kind === 'workbook'"
      :project-id="selectedProjectId"
      :document="currentDocument"
      @changed="loadDocuments"
    />
    <PresentationWorkspace
      v-else-if="studioMode === 'presentation' && currentDocument?.kind === 'presentation'"
      :project-id="selectedProjectId"
      :document="currentDocument"
      :initial-slide="presentationInitialSlide"
      @changed="loadDocuments"
      @navigate-to-thesis="navigateFromPresentation"
      @slide-changed="presentationInitialSlide = $event"
    />

    <el-empty v-else-if="!loading" description="请选择项目内文档，或新建正文、表格、PPT" />

    <el-dialog v-model="projectDialogVisible" :title="editingProjectId ? '编辑文档项目' : '新建文档项目'" width="720px">
      <div class="project-form">
        <div class="project-form-row title">
          <el-input v-model="projectForm.name" placeholder="文档名称" />
          <el-select v-model="projectForm.document_type" placeholder="文档类型">
            <el-option label="研究报告" value="研究报告" />
            <el-option label="学术论文" value="学术论文" />
            <el-option label="博士论文" value="博士论文" />
            <el-option label="技术报告" value="技术报告" />
            <el-option label="专利文档" value="专利文档" />
            <el-option label="项目方案" value="项目方案" />
          </el-select>
        </div>
        <el-input v-model="projectForm.description" type="textarea" :rows="2" placeholder="文档简介与使用需求" />
        <el-input v-model="projectForm.writing_goal" type="textarea" :rows="2" placeholder="写作目标" />
        <div class="project-form-row">
          <el-input v-model="projectForm.target_audience" placeholder="目标读者" />
          <el-input v-model="projectForm.output_format" placeholder="输出格式" />
        </div>
        <div class="project-form-row">
          <el-input v-model="projectForm.owner_agent" placeholder="负责智能体 ID" />
          <el-select v-model="projectForm.priority" placeholder="优先级">
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </div>
        <el-input
          v-model="projectOutlineText"
          type="textarea"
          :rows="7"
          placeholder="初始目录，每行一个章节，例如：&#10;第一章 项目背景&#10;第二章 方案设计&#10;第三章 实施计划"
        />
        <small v-if="editingProjectId" class="form-tip">修改目录计划不会覆盖已经存在的正文和版本记录。</small>
      </div>
      <template #footer>
        <el-button @click="projectDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="projectSaving" @click="saveProject">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="documentDialogVisible"
      :title="editingDocumentId ? '编辑项目文档' : '新增项目文档'"
      width="560px"
    >
      <div class="document-form">
        <el-input v-model="documentForm.title" placeholder="文档名称，例如：规则手册" />
        <el-radio-group v-model="documentForm.kind" :disabled="Boolean(editingDocumentId)">
          <el-radio-button value="rich_text">正文</el-radio-button>
          <el-radio-button value="workbook">Excel 表格</el-radio-button>
          <el-radio-button value="presentation">PPT 演示</el-radio-button>
        </el-radio-group>
        <el-input
          v-if="documentForm.kind === 'rich_text' && !editingDocumentId"
          v-model="documentOutlineText"
          type="textarea"
          :rows="6"
          placeholder="初始目录，每行一个章节"
        />
        <el-upload
          v-if="documentForm.kind !== 'rich_text' && !editingDocumentId"
          drag
          :auto-upload="false"
          :limit="1"
          :accept="documentForm.kind === 'workbook' ? '.xlsx' : '.pptx'"
          :on-change="handleDocumentFileChange"
          :on-remove="() => documentUploadFile = undefined"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">
            拖入或选择 {{ documentForm.kind === 'workbook' ? 'XLSX' : 'PPTX' }} 文件
          </div>
        </el-upload>
        <el-checkbox v-model="documentForm.is_primary" :disabled="documentForm.kind !== 'rich_text'">设为项目主文档</el-checkbox>
      </div>
      <template #footer>
        <el-button @click="documentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="documentSaving" @click="saveDocument">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="productionDialogVisible"
      title="课程正式交付检查"
      width="min(720px, 92vw)"
    >
      <div class="production-blocker-list">
        <div v-for="(blocker, index) in productionStatus?.blockers || []" :key="`${blocker.scope || 'course'}-${blocker.code}-${index}`">
          <el-tag size="small" type="warning" effect="plain">{{ blocker.scope || '课程基线' }}</el-tag>
          <span>{{ blocker.message }}</span>
        </div>
        <el-empty v-if="!productionStatus?.blockers.length" description="课程产品已满足正式交付条件" :image-size="56" />
      </div>
    </el-dialog>

    <el-dialog
      v-model="pdfPreviewVisible"
      title="PDF 预览"
      width="94vw"
      class="pdf-preview-dialog"
      destroy-on-close
    >
      <iframe v-if="pdfPreviewUrl" :src="pdfPreviewUrl" title="文档 PDF 预览" class="pdf-preview-frame" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MarkdownIt from 'markdown-it'
import * as echarts from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { ArrowDown, ArrowUp, Delete, Document, EditPen, FolderOpened, Grid, Plus, Refresh, Search, Tickets, UploadFilled, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteProject, getProjects, updateProject, type Project } from '@/api/projects'
import PresentationWorkspace from '@/components/writing/PresentationWorkspace.vue'
import WorkbookWorkspace from '@/components/writing/WorkbookWorkspace.vue'
import DocumentEvaluationPanel from '@/components/writing/DocumentEvaluationPanel.vue'
import DocumentLayoutPanel from '@/components/writing/DocumentLayoutPanel.vue'
import DocumentOutlineTree from '@/components/writing/DocumentOutlineTree.vue'
import DocumentStructureStatus from '@/components/writing/DocumentStructureStatus.vue'
import CollaborativeWritingEditor from '@/components/writing/CollaborativeWritingEditor.vue'
import WritingLinkedWorkspace from '@/components/writing/WritingLinkedWorkspace.vue'
import { documentVersionLabel, richTextDeliveryState, richTextOutputSummary } from '@/utils/documentDelivery'
import {
  createWritingDocument,
  createWritingProject,
  deleteWritingDocument,
  applyCourseProductTemplate,
  applyCourseWorkPlan,
  runCourseIteration,
  reviewCoursePoint,
  exportProjectWritingDocument,
  exportWritingProjectPackage,
  confirmDocumentEvaluation,
  getDocumentEvaluation,
  getDocumentEvaluationJob,
  getDocumentEvaluationProfile,
  getDocumentWritingAsset,
  getDocumentWritingFulltext,
  getDocumentWritingGraph,
  getDocumentWritingQuality,
  getDocumentWritingReferences,
  getDocumentWritingSection,
  getDocumentWritingSourceWord,
  getDocumentWritingVersions,
  getDocumentWritingWorkspace,
  getDocumentLayout,
  getDocumentLayoutDelivery,
  getDocumentLayoutSample,
  getWritingCollaboration,
  getPresentationManifest,
  getEvaluationProfiles,
  getLinkedDocumentEvaluationSummary,
  getCourseProductionStatus,
  getWritingDocuments,
  importWritingDocx,
  reorderWritingDocuments,
  replaceWritingDocumentContent,
  runDocumentEvaluation,
  updateDocumentEvaluationProfile,
  updateDocumentLayout,
  updateWritingDocument,
  type WritingDirectoryNode,
  type DocumentEvaluationProfile,
  type DocumentEvaluationReport,
  type DocumentLayoutState,
  type LinkedDocumentEvaluationSummary,
  type DocumentStructureBindingStatus,
  type PresentationManifest,
  type CourseProductionStatus,
  type CourseWorkPoint,
  type WritingGraphNode,
  type WritingProjectDocument,
  type WritingProjectDocuments,
  type WritingPublicationStatus,
  type WritingReference,
  type WritingReferenceCoverage,
  type WritingSection,
  type WritingWorkspace,
  type WritingDocumentKind
} from '@/api/writing'

echarts.use([GraphChart, LegendComponent, TooltipComponent, CanvasRenderer])

const route = useRoute()
const router = useRouter()
const md = new MarkdownIt({ html: false, linkify: true, breaks: false })
md.renderer.rules.heading_open = (
  tokens: Array<{ map?: [number, number]; attrSet: (name: string, value: string) => void }>,
  index: number,
  options: Record<string, unknown>,
  env: { sectionId?: string },
  renderer: { renderToken: (items: unknown[], itemIndex: number, renderOptions: Record<string, unknown>) => string }
) => {
  const token = tokens[index]
  const sectionId = String((env as { sectionId?: string })?.sectionId || '')
  if (sectionId && token.map) token.attrSet('id', `${sectionId}-heading-${token.map[0] + 1}`)
  return renderer.renderToken(tokens, index, options)
}
const projects = ref<Project[]>([])
const projectSearch = ref('')
const selectedProjectId = ref('')
const selectedDocumentId = ref('')
const documentCollection = ref<WritingProjectDocuments>()
const productionStatus = ref<CourseProductionStatus>()
const productionDialogVisible = ref(false)
const applyingCourseTemplate = ref(false)
const syncingCourseWorkPlan = ref(false)
const runningCourseIteration = ref(false)
const reviewingCoursePointId = ref('')
const courseIterationRounds = ref(1)
const courseIterationParallelism = ref(3)
const importingDocx = ref(false)
const presentationManifests = ref<Record<string, PresentationManifest>>({})
const presentationInitialSlide = ref(1)
const studioMode = ref<'document' | 'presentation' | 'linked' | 'workbook'>('document')
const linkedPresentationDocumentId = ref('')
const formalDocuments = computed(() => (
  documentCollection.value?.documents.filter(row => row.is_output_product) || []
))
const internalDataSources = computed(() => (
  documentCollection.value?.documents.filter(row => !row.is_output_product) || []
))
const richTextDocuments = computed(() => (
  documentCollection.value?.documents.filter(row => row.kind === 'rich_text' && row.status === 'active') || []
))
const presentationDocuments = computed(() => (
  documentCollection.value?.documents.filter(row => row.kind === 'presentation' && row.status === 'active') || []
))
const documentOrderCount = computed(() => documentCollection.value?.documents.length || 0)
const selectedProject = computed(() => projects.value.find(row => row.id === selectedProjectId.value))
const isCourseProject = computed(() => {
  const project = selectedProject.value
  return Boolean(
    project?.document_spec?.course_profile?.template_key
    || project?.document_spec?.document_type === '课程教学产品组合'
    || String(project?.name || '').includes('水面舰艇作战软件与兵棋推演')
  )
})
const courseAttentionPoints = computed<CourseWorkPoint[]>(() => (
  (productionStatus.value?.work_plan?.workstreams || [])
    .flatMap(workstream => workstream.point_items || [])
    .filter(point => ['ready', 'in_progress', 'running', 'review', 'blocked'].includes(point.status))
    .sort((left, right) => {
      const rank: Record<string, number> = {
        review: 0,
        blocked: 1,
        in_progress: 2,
        running: 2,
        ready: 3
      }
      return (rank[left.status] ?? 9) - (rank[right.status] ?? 9)
        || (left.iteration || 0) - (right.iteration || 0)
    })
    .slice(0, 12)
))
const showArchivedDocuments = ref(false)
const documentDialogVisible = ref(false)
const documentSaving = ref(false)
const editingDocumentId = ref('')
const documentOutlineText = ref('')
const documentUploadFile = ref<File>()
const documentForm = ref<{ title: string; kind: WritingDocumentKind; is_primary: boolean }>({
  title: '',
  kind: 'rich_text',
  is_primary: false
})
const projectDialogVisible = ref(false)
const projectSaving = ref(false)
const editingProjectId = ref('')
const projectOutlineText = ref('')
const projectForm = ref({
  name: '',
  description: '',
  document_type: '研究报告',
  writing_goal: '',
  target_audience: '',
  output_format: 'Markdown / Word / PDF',
  owner_agent: 'ultra-magnus',
  priority: 'medium'
})
const workspace = ref<WritingWorkspace>()
const evaluationProfile = ref<DocumentEvaluationProfile>()
const evaluationReport = ref<DocumentEvaluationReport>()
const linkedEvaluationSummary = ref<LinkedDocumentEvaluationSummary>()
const evaluationProfiles = ref<Array<{
  id: string
  name: string
  version: string
  kind: WritingDocumentKind
}>>([])
const evaluationBusy = ref(false)
let evaluationPollTimer: ReturnType<typeof setTimeout> | undefined
const currentDocument = computed(() => documentCollection.value?.documents.find(row => row.id === selectedDocumentId.value))
const linkedPresentationDocument = computed(() => (
  presentationDocuments.value.find(row => row.id === linkedPresentationDocumentId.value)
  || presentationDocuments.value.find(row => row.structure_binding?.source_document_id === currentDocument.value?.id)
  || presentationDocuments.value[0]
))
const currentContentVersionLabel = computed(() => currentDocument.value
  ? documentVersionLabel(currentDocument.value)
  : `v${workspace.value?.manifest.version || 1}`)
const sectionDeliveryStatus = (section: WritingSection) => {
  if (currentDocument.value?.publication_status === 'approved' || currentDocument.value?.publication_status === 'published') {
    return { label: '已成稿', type: 'success' as const }
  }
  return section.status === 'writing'
    ? { label: '有正文', type: 'success' as const }
    : { label: '待充实', type: 'warning' as const }
}
const currentStructure = computed(() => workspace.value?.current_structure)
const targetStructure = computed(() => workspace.value?.project.document_spec?.target_structure)
const documentSpec = computed(() => workspace.value?.project.document_spec || {})
const isThesisDocument = computed(() => {
  const type = String(documentSpec.value.document_type || '')
  return type.includes('论文') || String(currentDocument.value?.title || '').includes('论文')
})
const overviewProfileTitle = computed(() => isThesisDocument.value ? '论文研究画像' : `${currentDocument.value?.title || '文档'}撰写画像`)
const deliveryGuidance = computed(() => isThesisDocument.value
  ? '第三版 Markdown 是当前内容权威，出版版 Word/PDF 是交付权威；Obsidian 正式版作为第二版历史基线保留，用于版本追溯和结构对比。'
  : 'Markdown 工作稿是当前内容权威，Word/PDF 是排版与交付权威；每次章节保存都会生成可追溯版本。')
const currentEditionLabel = computed(() => documentSpec.value.current_edition_label || workspace.value?.manifest.edition || '第三版')
const obsidianEditionLabel = computed(() => documentSpec.value.obsidian_edition_label || '第二版')
const publicationEditionLabel = computed(() => documentSpec.value.publication_edition_label || '出版版')
const publicationStructureTitle = computed(() => {
  return currentStructure.value?.title || targetStructure.value?.title || '当前文档结构'
})
const publicationStructureVersion = computed(() => {
  const version = currentStructure.value?.version || ''
  return version || `${publicationEditionLabel.value}目录基线`
})
const versionStages = computed(() => [
  {
    key: 'v1',
    label: '第一版',
    title: '初始目录基线',
    description: '保留最早的研究设想、章节范围和问题拆解，用于回看论文立题原点。',
    meta: '历史参照',
    state: 'history'
  },
  {
    key: 'v2',
    label: obsidianEditionLabel.value,
    title: 'Obsidian 正式版',
    description: '知识库中沉淀的正式论文章节版本，作为第一版之后的稳定演进基线。',
    meta: '正式沉淀',
    state: 'baseline'
  },
  {
    key: 'v3',
    label: currentEditionLabel.value,
    title: '当前工作稿',
    description: `当前 ${workspace.value?.stats.chapter_count || 0} 章正文，持续承载写作、引用、图表和质量检查。`,
    meta: `${currentContentVersionLabel.value} · 协同修订 r${workspace.value?.manifest.version || 0}`,
    state: 'current'
  },
  {
    key: 'publication',
    label: publicationEditionLabel.value,
    title: `${targetStructure.value?.chapter_count || 0}章目标结构`,
    description: `${targetStructure.value?.chapter_count || 0} 章、${targetStructure.value?.heading_count || 0} 个目录项，是当前修改与送审交付的结构目标。`,
    meta: '交付目标',
    state: 'target'
  }
])
const activeView = ref('overview')
const loading = ref(false)
const sectionLoading = ref(false)
const selectedSectionId = ref('')
const selectedDirectoryNodeId = ref('')
const currentSection = ref<WritingSection>()
const readerMode = ref<'section' | 'full'>('section')
const displayMarkdown = ref('')
const documentBody = ref<HTMLElement>()
const collaborationEditor = ref<InstanceType<typeof CollaborativeWritingEditor>>()
const references = ref<Awaited<ReturnType<typeof getDocumentWritingReferences>>>()
const referenceSearch = ref('')
const referenceStatus = ref<'all' | 'cited' | 'uncited'>('all')
const graphData = ref<Awaited<ReturnType<typeof getDocumentWritingGraph>>>()
const graphMode = ref('concept')
const graphElement = ref<HTMLElement>()
const selectedGraphNode = ref<WritingGraphNode>()
const qualityReport = ref<Awaited<ReturnType<typeof getDocumentWritingQuality>>>()
const versions = ref<Array<{ name: string; size_bytes: number; created_at: string; current?: boolean }>>([])
const layoutState = ref<DocumentLayoutState>()
const layoutSaving = ref(false)
const exporting = ref('')
const exportingPackage = ref(false)
const objectUrls = ref<string[]>([])
const pdfPreviewVisible = ref(false)
const pdfPreviewUrl = ref('')
let graphChart: echarts.ECharts | undefined

const readerModes = [{ label: '章节阅读', value: 'section' }, { label: '全文阅读', value: 'full' }]
const graphModes = [{ label: '概念骨架', value: 'concept' }, { label: '论证关系', value: 'argument' }]
const referenceStatusOptions = [{ label: '全部', value: 'all' }, { label: '已引用', value: 'cited' }, { label: '未检出', value: 'uncited' }]
const filteredProjects = computed(() => {
  const keyword = projectSearch.value.trim().toLowerCase()
  const rows = [...projects.value].sort((a, b) => {
    if (a.status === 'archived' && b.status !== 'archived') return 1
    if (a.status !== 'archived' && b.status === 'archived') return -1
    return a.name.localeCompare(b.name, 'zh-CN')
  })
  if (!keyword) return rows
  return rows.filter(project => [
    project.name,
    project.description || '',
    project.document_spec?.document_type || '',
    project.owner_agent || ''
  ].some(value => value.toLowerCase().includes(keyword)))
})
const chapterSections = computed(() => workspace.value?.sections.filter(row => row.kind === 'chapter') || [])
const activeSectionMeta = computed(() => workspace.value?.sections.find(row => row.id === selectedSectionId.value))
const activeDirectoryNode = computed(() => (
  findDirectoryNode(workspace.value?.directory || [], selectedDirectoryNodeId.value)
))
const linkedPresentationSlides = computed(() => {
  const sourceDocumentId = currentDocument.value?.kind === 'rich_text'
    ? currentDocument.value.id
    : ''
  if (!sourceDocumentId) return []
  const token = outlineNumber(
    activeDirectoryNode.value?.title || activeSectionMeta.value?.title || ''
  )
  if (!token) return []
  return Object.entries(presentationManifests.value)
    .filter(([, manifest]) => manifest.structure_binding?.source_document_id === sourceDocumentId)
    .flatMap(([documentId, manifest]) => (
      manifest.slides
        .filter(slide => slide.thesis_sections.some(section => sectionMatchesOutline(section, token)))
        .map(slide => ({
          documentId,
          slide: slide.slide,
          title: slide.title,
          appendix: slide.appendix
        }))
    ))
    .sort((left, right) => left.slide - right.slide)
})
const renderedDocument = computed(() => md.render(
  displayMarkdown.value || '*暂无正文*',
  { sectionId: readerMode.value === 'section' ? selectedSectionId.value : '' }
))
const qualityClass = computed(() => {
  const score = workspace.value?.quality.score || 0
  if (score >= 85) return 'quality-good'
  if (score >= 60) return 'quality-warning'
  return 'quality-danger'
})
const filteredFormalReferences = computed(() => filterReferences(references.value?.formal || []).filter(row => {
  if (referenceStatus.value === 'cited') return Boolean(row.usage_count)
  if (referenceStatus.value === 'uncited') return !row.usage_count
  return true
}))
const filteredKnowledgeReferences = computed(() => filterReferences(references.value?.knowledge || []))

async function loadProjects() {
  const result = await getProjects({ project_type: 'document', enabled_module: 'writing' })
  projects.value = result.projects || []
}

async function loadDocuments() {
  if (!selectedProjectId.value) {
    documentCollection.value = undefined
    productionStatus.value = undefined
    selectedDocumentId.value = ''
    return
  }
  documentCollection.value = await getWritingDocuments(selectedProjectId.value, showArchivedDocuments.value)
  if (isCourseProject.value) {
    productionStatus.value = await getCourseProductionStatus(selectedProjectId.value)
  } else {
    productionStatus.value = undefined
  }
  const manifests: Record<string, PresentationManifest> = {}
  await Promise.all(documentCollection.value.documents
    .filter(row => row.kind === 'presentation')
    .map(async row => {
      try {
        manifests[row.id] = await getPresentationManifest(selectedProjectId.value, row.id)
      } catch {
        // A presentation without a manifest remains visible with a "not bound" status.
      }
    }))
  presentationManifests.value = manifests
  if (!presentationDocuments.value.some(row => row.id === linkedPresentationDocumentId.value)) {
    linkedPresentationDocumentId.value = presentationDocuments.value[0]?.id || ''
  }
  const routeDocumentId = String(route.query.document_id || '')
  const rows = documentCollection.value.documents
  selectedDocumentId.value = rows.some(row => row.id === routeDocumentId)
    ? routeDocumentId
    : rows.some(row => row.id === selectedDocumentId.value)
      ? selectedDocumentId.value
      : rows.find(row => row.is_primary && row.status === 'active')?.id
        || rows.find(row => row.status === 'active')?.id
        || rows[0]?.id
        || ''
  const selectedKind = rows.find(row => row.id === selectedDocumentId.value)?.kind
  if (selectedKind === 'presentation') studioMode.value = 'presentation'
  else if (selectedKind === 'workbook') studioMode.value = 'workbook'
  else studioMode.value = 'document'
}

function clearEvaluationPolling() {
  if (evaluationPollTimer) clearTimeout(evaluationPollTimer)
  evaluationPollTimer = undefined
}

async function loadEvaluation() {
  if (!selectedProjectId.value || !selectedDocumentId.value) {
    evaluationProfile.value = undefined
    evaluationReport.value = undefined
    linkedEvaluationSummary.value = undefined
    return
  }
  const projectId = selectedProjectId.value
  const documentId = selectedDocumentId.value
  const [profile, report, linked, catalog] = await Promise.all([
    getDocumentEvaluationProfile(projectId, documentId),
    getDocumentEvaluation(projectId, documentId),
    getLinkedDocumentEvaluationSummary(projectId),
    evaluationProfiles.value.length ? Promise.resolve(undefined) : getEvaluationProfiles()
  ])
  if (projectId !== selectedProjectId.value || documentId !== selectedDocumentId.value) return
  evaluationProfile.value = profile
  evaluationReport.value = report
  linkedEvaluationSummary.value = linked
  if (catalog) evaluationProfiles.value = catalog.profiles
}

async function pollEvaluationJob(jobId: string, attempt = 0) {
  clearEvaluationPolling()
  const projectId = selectedProjectId.value
  const documentId = selectedDocumentId.value
  if (!projectId || !documentId) return
  try {
    const job = await getDocumentEvaluationJob(projectId, documentId, jobId)
    if (projectId !== selectedProjectId.value || documentId !== selectedDocumentId.value) return
    if (!job || ['succeeded', 'failed'].includes(job.status)) {
      await loadEvaluation()
      evaluationBusy.value = false
      if (job?.status === 'succeeded') ElMessage.success('完整文档评价已完成')
      if (job?.status === 'failed') ElMessage.warning(job.error || '学术评价未完成，已保留技术检查结果')
      return
    }
    if (attempt >= 200) {
      evaluationBusy.value = false
      ElMessage.warning('评价仍在后台执行，可稍后刷新查看')
      return
    }
    evaluationPollTimer = setTimeout(() => pollEvaluationJob(jobId, attempt + 1), 3000)
  } catch (error) {
    evaluationBusy.value = false
    ElMessage.error(errorMessage(error, '评价任务状态读取失败'))
  }
}

async function runEvaluation(mode: 'technical' | 'full') {
  if (!selectedProjectId.value || !selectedDocumentId.value) return
  evaluationBusy.value = true
  try {
    const result = await runDocumentEvaluation(
      selectedProjectId.value,
      selectedDocumentId.value,
      mode
    )
    evaluationReport.value = result.report
    if (result.job) {
      ElMessage.info('完整评价已进入后台，将逐章分析并汇总')
      await pollEvaluationJob(result.job.id)
    } else {
      await loadEvaluation()
      evaluationBusy.value = false
      ElMessage.success('技术完整度已刷新')
    }
  } catch (error) {
    evaluationBusy.value = false
    ElMessage.error(errorMessage(error, '文档评价启动失败'))
  }
}

async function confirmEvaluation(payload: {
  dimension_scores: Record<string, number>
  gate_statuses: Record<string, 'pass' | 'fail' | 'not_applicable'>
  comment: string
}) {
  evaluationBusy.value = true
  try {
    evaluationReport.value = await confirmDocumentEvaluation(
      selectedProjectId.value,
      selectedDocumentId.value,
      { ...payload, actor: 'admin' }
    )
    linkedEvaluationSummary.value = await getLinkedDocumentEvaluationSummary(selectedProjectId.value)
    ElMessage.success('专家确认已保存并写入审计记录')
  } catch (error) {
    ElMessage.error(errorMessage(error, '专家确认保存失败'))
  } finally {
    evaluationBusy.value = false
  }
}

async function saveEvaluationProfile(payload: {
  profile_id: string
  overrides: {
    pass_threshold: number
    dimension_weights: Record<string, number>
    dimension_min_scores: Record<string, number>
    gate_required: Record<string, boolean>
  }
}) {
  evaluationBusy.value = true
  try {
    evaluationProfile.value = await updateDocumentEvaluationProfile(
      selectedProjectId.value,
      selectedDocumentId.value,
      { ...payload, actor: 'admin' }
    )
    const result = await runDocumentEvaluation(
      selectedProjectId.value,
      selectedDocumentId.value,
      'technical'
    )
    evaluationReport.value = result.report
    linkedEvaluationSummary.value = await getLinkedDocumentEvaluationSummary(selectedProjectId.value)
    ElMessage.success('项目评价标准已更新，旧学术评价已失效')
  } catch (error) {
    ElMessage.error(errorMessage(error, '评价标准保存失败'))
  } finally {
    evaluationBusy.value = false
  }
}

async function loadWorkspace() {
  loading.value = true
  try {
    if (!projects.value.length) await loadProjects()
    const routeProjectId = String(route.query.project_id || '')
    selectedProjectId.value = projects.value.some(row => row.id === routeProjectId)
      ? routeProjectId
      : projects.value.some(row => row.id === selectedProjectId.value)
        ? selectedProjectId.value
        : projects.value.find(row => row.status !== 'archived')?.id || projects.value[0]?.id || ''
    if (!selectedProjectId.value) {
      workspace.value = undefined
      return
    }
    await loadDocuments()
    if (!selectedDocumentId.value || currentDocument.value?.kind !== 'rich_text') {
      workspace.value = undefined
      return
    }
    workspace.value = await getDocumentWritingWorkspace(selectedProjectId.value, selectedDocumentId.value)
    await loadEvaluation()
    selectedSectionId.value = workspace.value.sections.find(row => row.kind === 'chapter')?.id || workspace.value.sections[0]?.id || ''
    selectedDirectoryNodeId.value = selectedSectionId.value
    if (selectedSectionId.value) await loadSection(selectedSectionId.value)
  } catch (error) {
    ElMessage.error(errorMessage(error, '文档工作台加载失败'))
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  try {
    await loadProjects()
    await loadWorkspace()
    ElMessage.success('文档项目已刷新')
  } catch (error) {
    ElMessage.error(errorMessage(error, '文档项目刷新失败'))
  }
}

async function selectProject(projectId: string) {
  if (selectedProjectId.value === projectId && workspace.value) return
  selectedProjectId.value = projectId
  await changeProject()
}

async function changeProject() {
  clearEvaluationPolling()
  selectedDocumentId.value = ''
  documentCollection.value = undefined
  await router.replace({ path: '/writing', query: { project_id: selectedProjectId.value } })
  workspace.value = undefined
  references.value = undefined
  graphData.value = undefined
  evaluationProfile.value = undefined
  evaluationReport.value = undefined
  linkedEvaluationSummary.value = undefined
  await loadWorkspace()
}

async function handleStudioModeChange(value: string | number) {
  const nextMode = String(value) as typeof studioMode.value
  if (nextMode === 'linked') {
    const sourceDocument = currentDocument.value?.kind === 'rich_text'
      ? currentDocument.value
      : richTextDocuments.value.find(row => row.is_primary) || richTextDocuments.value[0]
    if (!sourceDocument) return
    const linkedPresentation = presentationDocuments.value.find(row => (
      row.structure_binding?.source_document_id === sourceDocument.id
    )) || presentationDocuments.value[0]
    linkedPresentationDocumentId.value = linkedPresentation?.id || ''
    studioMode.value = 'linked'
    await selectDocument(sourceDocument.id, undefined, true)
    studioMode.value = 'linked'
    return
  }
  if (nextMode === 'presentation') {
    const presentation = currentDocument.value?.kind === 'presentation'
      ? currentDocument.value
      : linkedPresentationDocument.value || presentationDocuments.value[0]
    if (presentation) await selectDocument(presentation.id)
    return
  }
  if (nextMode === 'document') {
    const sourceDocument = currentDocument.value?.kind === 'rich_text'
      ? currentDocument.value
      : richTextDocuments.value.find(row => row.is_primary) || richTextDocuments.value[0]
    if (sourceDocument) await selectDocument(sourceDocument.id)
  }
}

async function selectDocument(documentId: string, initialSlide?: number, preserveStudioMode = false) {
  if (
    selectedDocumentId.value === documentId
    && String(route.query.document_id || '') === documentId
    && (currentDocument.value?.kind !== 'rich_text' || Boolean(workspace.value))
  ) return
  clearEvaluationPolling()
  selectedDocumentId.value = documentId
  const nextDocument = documentCollection.value?.documents.find(row => row.id === documentId)
  if (nextDocument?.kind === 'presentation') {
    presentationInitialSlide.value = Math.max(1, Number(initialSlide || 1))
    linkedPresentationDocumentId.value = nextDocument.id
  }
  if (!preserveStudioMode) {
    studioMode.value = nextDocument?.kind === 'presentation'
      ? 'presentation'
      : nextDocument?.kind === 'workbook'
        ? 'workbook'
        : 'document'
  }
  workspace.value = undefined
  references.value = undefined
  graphData.value = undefined
  qualityReport.value = undefined
  versions.value = []
  evaluationProfile.value = undefined
  evaluationReport.value = undefined
  linkedEvaluationSummary.value = undefined
  activeView.value = 'overview'
  await router.replace({
    path: '/writing',
    query: { project_id: selectedProjectId.value, document_id: documentId }
  })
  if (currentDocument.value?.kind === 'rich_text') await loadWorkspace()
}

async function handleLinkedWorkspaceChanged(kind: 'document' | 'presentation') {
  if (kind === 'presentation') {
    const previousMode = studioMode.value
    await loadDocuments()
    studioMode.value = previousMode
  }
}

function splitOutline(value: string) {
  return value.split(/\r?\n/).map(row => row.trim()).filter(Boolean)
}

function openProjectDialog(project?: Project) {
  editingProjectId.value = project?.id || ''
  projectForm.value = {
    name: project?.name || '',
    description: project?.description || '',
    document_type: project?.document_spec?.document_type || '研究报告',
    writing_goal: project?.document_spec?.writing_goal || '',
    target_audience: project?.document_spec?.target_audience || '',
    output_format: project?.document_spec?.output_format || 'Markdown / Word / PDF',
    owner_agent: project?.owner_agent || 'ultra-magnus',
    priority: project?.priority || 'medium'
  }
  projectOutlineText.value = (project?.document_spec?.outline || []).join('\n')
  projectDialogVisible.value = true
}

async function saveProject() {
  if (!projectForm.value.name.trim()) {
    ElMessage.warning('请填写文档名称')
    return
  }
  projectSaving.value = true
  try {
    const outline = splitOutline(projectOutlineText.value)
    if (editingProjectId.value) {
      const existing = projects.value.find(row => row.id === editingProjectId.value)
      await updateProject(editingProjectId.value, {
        name: projectForm.value.name.trim(),
        description: projectForm.value.description.trim(),
        priority: projectForm.value.priority,
        owner_agent: projectForm.value.owner_agent.trim() || 'ultra-magnus',
        document_spec: {
          ...(existing?.document_spec || {}),
          document_type: projectForm.value.document_type,
          writing_goal: projectForm.value.writing_goal.trim(),
          target_audience: projectForm.value.target_audience.trim(),
          output_format: projectForm.value.output_format.trim() || 'Markdown / Word / PDF',
          outline
        }
      })
      selectedProjectId.value = editingProjectId.value
      ElMessage.success('文档项目信息已更新')
    } else {
      const result = await createWritingProject({
        ...projectForm.value,
        outline
      })
      selectedProjectId.value = result.project.id
      ElMessage.success('新文档及独立工作区已创建')
    }
    projectDialogVisible.value = false
    await loadProjects()
    await changeProject()
  } catch (error) {
    ElMessage.error(errorMessage(error, '文档项目保存失败'))
  } finally {
    projectSaving.value = false
  }
}

async function toggleProjectArchive(project: Project) {
  const restoring = project.status === 'archived'
  try {
    await updateProject(project.id, { status: restoring ? 'planning' : 'archived' })
    await loadProjects()
    if (!restoring && selectedProjectId.value === project.id) {
      const next = projects.value.find(row => row.status !== 'archived' && row.id !== project.id)
      if (next) {
        selectedProjectId.value = next.id
        await changeProject()
      }
    }
    ElMessage.success(restoring ? '文档已恢复' : '文档已归档')
  } catch (error) {
    ElMessage.error(errorMessage(error, restoring ? '恢复失败' : '归档失败'))
  }
}

async function removeProject(project: Project) {
  try {
    await ElMessageBox.confirm(
      `永久删除“${project.name}”的项目记录？已生成的正文文件将保留在知识库中。`,
      '删除文档项目',
      { type: 'warning', confirmButtonText: '永久删除', cancelButtonText: '取消' }
    )
    await deleteProject(project.id)
    if (selectedProjectId.value === project.id) {
      selectedProjectId.value = ''
      workspace.value = undefined
    }
    await loadProjects()
    await loadWorkspace()
    ElMessage.success('文档项目记录已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error, '删除失败'))
  }
}

function openDocumentDialog(documentItem?: WritingProjectDocument) {
  editingDocumentId.value = documentItem?.id || ''
  documentForm.value = {
    title: documentItem?.title || '',
    kind: documentItem?.kind || 'rich_text',
    is_primary: Boolean(documentItem?.is_primary)
  }
  documentOutlineText.value = ''
  documentUploadFile.value = undefined
  documentDialogVisible.value = true
}

function handleDocumentFileChange(file: any) {
  documentUploadFile.value = file.raw as File
}

async function saveDocument() {
  if (!selectedProjectId.value || !documentForm.value.title.trim()) {
    ElMessage.warning('请填写文档名称')
    return
  }
  if (!editingDocumentId.value && documentForm.value.kind !== 'rich_text' && !documentUploadFile.value) {
    ElMessage.warning(`请选择 ${documentForm.value.kind === 'workbook' ? 'XLSX' : 'PPTX'} 文件`)
    return
  }
  documentSaving.value = true
  try {
    let documentItem: WritingProjectDocument
    if (editingDocumentId.value) {
      documentItem = await updateWritingDocument(selectedProjectId.value, editingDocumentId.value, {
        title: documentForm.value.title.trim(),
        is_primary: documentForm.value.kind === 'rich_text' ? documentForm.value.is_primary : false
      })
      ElMessage.success('文档信息已更新')
    } else {
      documentItem = await createWritingDocument(selectedProjectId.value, {
        title: documentForm.value.title.trim(),
        kind: documentForm.value.kind,
        outline: splitOutline(documentOutlineText.value),
        is_primary: documentForm.value.kind === 'rich_text' && documentForm.value.is_primary
      })
      if (documentUploadFile.value) {
        documentItem = await replaceWritingDocumentContent(selectedProjectId.value, documentItem.id, documentUploadFile.value)
      }
      ElMessage.success('项目文档已创建')
    }
    selectedDocumentId.value = documentItem.id
    documentDialogVisible.value = false
    await loadDocuments()
    await selectDocument(documentItem.id)
  } catch (error) {
    ElMessage.error(errorMessage(error, '项目文档保存失败'))
  } finally {
    documentSaving.value = false
  }
}

async function applyCourseTemplate() {
  if (!selectedProjectId.value) return
  applyingCourseTemplate.value = true
  try {
    const result = await applyCourseProductTemplate(selectedProjectId.value)
    await loadProjects()
    await loadDocuments()
    ElMessage.success(`20学时模板已对齐：新增 ${result.summary.create} 项，更新 ${result.summary.update} 项`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '20学时课程模板应用失败'))
  } finally {
    applyingCourseTemplate.value = false
  }
}

async function syncCourseWorkPlan() {
  if (!selectedProjectId.value) return
  syncingCourseWorkPlan.value = true
  try {
    const result = await applyCourseWorkPlan(selectedProjectId.value)
    productionStatus.value = await getCourseProductionStatus(selectedProjectId.value)
    ElMessage.success(
      `课程任务已同步：新增 ${result.summary.create} 项，更新 ${result.summary.update} 项，补充 ${result.summary.points_added} 个执行要点`
    )
  } catch (error) {
    ElMessage.error(errorMessage(error, '课程任务同步失败'))
  } finally {
    syncingCourseWorkPlan.value = false
  }
}

async function executeCourseIteration() {
  if (!selectedProjectId.value) return
  const eligible = productionStatus.value?.work_plan?.execution?.eligible_points || 0
  if (!eligible) {
    ElMessage.warning('当前没有满足依赖条件的课程要点')
    return
  }
  const maximum = Math.min(
    eligible,
    courseIterationRounds.value * courseIterationParallelism.value
  )
  try {
    await ElMessageBox.confirm(
      `将执行 ${courseIterationRounds.value} 轮，最多释放 ${maximum} 个课程要点。`,
      '执行课程迭代',
      {
        confirmButtonText: '开始执行',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }
  runningCourseIteration.value = true
  try {
    const result = await runCourseIteration(selectedProjectId.value, {
      rounds: courseIterationRounds.value,
      parallelism: courseIterationParallelism.value
    })
    productionStatus.value = await getCourseProductionStatus(selectedProjectId.value)
    ElMessage.success(
      `已启动第 ${result.iteration.iteration_start}`
      + `${result.iteration.iteration_end > result.iteration.iteration_start ? `-${result.iteration.iteration_end}` : ''}`
      + ` 轮，共 ${result.iteration.point_count} 个要点`
    )
  } catch (error) {
    ElMessage.error(errorMessage(error, '课程迭代启动失败'))
  } finally {
    runningCourseIteration.value = false
  }
}

async function reviewCourseExecutionPoint(
  point: CourseWorkPoint,
  decision: 'approve' | 'reject' | 'retry'
) {
  if (!selectedProjectId.value) return
  let comment = ''
  try {
    if (decision === 'reject') {
      const result = await ElMessageBox.prompt(
        '填写退回原因和需要补充的证据。',
        '退回课程要点',
        {
          confirmButtonText: '退回修改',
          cancelButtonText: '取消',
          inputValidator: value => Boolean(String(value || '').trim()) || '请填写退回原因'
        }
      )
      comment = String(result.value || '').trim()
    } else {
      await ElMessageBox.confirm(
        decision === 'approve'
          ? `确认“${point.title}”的执行证据满足验收要求？`
          : `确认将“${point.title}”重新加入可执行队列？`,
        decision === 'approve' ? '评审通过' : '重新排队',
        {
          confirmButtonText: decision === 'approve' ? '确认通过' : '确认排队',
          cancelButtonText: '取消',
          type: decision === 'approve' ? 'success' : 'warning'
        }
      )
    }
  } catch {
    return
  }
  reviewingCoursePointId.value = point.id
  try {
    await reviewCoursePoint(
      selectedProjectId.value,
      point.id,
      decision,
      comment
    )
    productionStatus.value = await getCourseProductionStatus(selectedProjectId.value)
    ElMessage.success(
      decision === 'approve'
        ? '课程要点已评审通过'
        : decision === 'reject'
          ? '课程要点已退回修改'
          : '课程要点已重新排队'
    )
  } catch (error) {
    ElMessage.error(errorMessage(error, '课程要点状态更新失败'))
  } finally {
    reviewingCoursePointId.value = ''
  }
}

async function importCourseDocx(uploadFile: any) {
  const file = uploadFile?.raw as File | undefined
  if (!selectedProjectId.value || !file) return
  importingDocx.value = true
  try {
    const title = file.name.replace(/\.docx$/i, '').trim() || '课程教学材料'
    const documentItem = await importWritingDocx(selectedProjectId.value, file, { title })
    await loadDocuments()
    await selectDocument(documentItem.id)
    ElMessage.success(`已导入“${title}”，原始Word、表格和图片均已保留`)
  } catch (error) {
    ElMessage.error(errorMessage(error, 'Word教学材料导入失败'))
  } finally {
    importingDocx.value = false
  }
}

async function toggleDocumentArchive(documentItem: WritingProjectDocument) {
  const restoring = documentItem.status === 'archived'
  try {
    await updateWritingDocument(selectedProjectId.value, documentItem.id, { status: restoring ? 'active' : 'archived' })
    ElMessage.success(restoring ? '文档已恢复' : '文档已归档')
    if (!restoring && selectedDocumentId.value === documentItem.id) selectedDocumentId.value = ''
    await loadDocuments()
    if (currentDocument.value?.kind === 'rich_text') await loadWorkspace()
  } catch (error) {
    ElMessage.error(errorMessage(error, restoring ? '恢复文档失败' : '归档文档失败'))
  }
}

async function moveDocument(documentItem: WritingProjectDocument, direction: -1 | 1) {
  try {
    const allDocuments = await getWritingDocuments(selectedProjectId.value, true)
    const ids = allDocuments.documents.map(row => row.id)
    const currentIndex = ids.indexOf(documentItem.id)
    const targetIndex = currentIndex + direction
    if (currentIndex < 0 || targetIndex < 0 || targetIndex >= ids.length) return
    const [moved] = ids.splice(currentIndex, 1)
    ids.splice(targetIndex, 0, moved)
    await reorderWritingDocuments(selectedProjectId.value, ids)
    await loadDocuments()
    ElMessage.success('文档顺序已更新')
  } catch (error) {
    ElMessage.error(errorMessage(error, '文档排序失败'))
  }
}

async function removeDocument(documentItem: WritingProjectDocument) {
  try {
    await ElMessageBox.confirm(
      `永久删除“${documentItem.title}”及其项目内版本文件？`,
      '永久删除项目文档',
      { type: 'warning', confirmButtonText: '永久删除', cancelButtonText: '取消' }
    )
    await deleteWritingDocument(selectedProjectId.value, documentItem.id)
    if (selectedDocumentId.value === documentItem.id) selectedDocumentId.value = ''
    await loadDocuments()
    if (currentDocument.value?.kind === 'rich_text') await loadWorkspace()
    ElMessage.success('项目文档已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(errorMessage(error, '删除文档失败'))
  }
}

function documentKindIcon(kind: WritingDocumentKind) {
  return kind === 'workbook' ? Grid : kind === 'presentation' ? VideoPlay : Document
}

function documentKindLabel(kind: WritingDocumentKind) {
  return ({ rich_text: '正文文档', workbook: 'Excel 表格', presentation: 'PPT 演示' } as Record<string, string>)[kind] || kind
}

function courseAgentName(agentId: string) {
  return ({
    optimus: '擎天柱',
    'ultra-magnus': '通天晓',
    wheeljack: '千斤顶',
    ironhide: '铁皮',
    ratchet: '救护车',
    perceptor: '感知器',
    donatello: '多纳泰罗',
    michelangelo: '米开朗基罗',
    raphael: '拉斐尔',
    leonardo: '李奥纳多'
  } as Record<string, string>)[agentId] || agentId || '待分配'
}

function courseWorkStatusLabel(status: string) {
  return ({
    todo: '待释放',
    ready: '已排队',
    in_progress: '执行中',
    running: '执行中',
    review: '待评审',
    blocked: '已阻塞',
    done: '已完成',
    completed: '已完成'
  } as Record<string, string>)[status] || status || '待分配'
}

function courseWorkStatusType(status: string) {
  if (['done', 'completed'].includes(status)) return 'success'
  if (status === 'review') return 'warning'
  if (status === 'blocked') return 'danger'
  if (['ready', 'in_progress', 'running'].includes(status)) return 'primary'
  return 'info'
}

function courseProductLabel(productType: string) {
  return ({
    course_plan: '教学计划',
    teaching_schedule: '进度表',
    lesson_plan: '教案',
    practice_guide: '实作指导书',
    assessment: '考核方案',
    course_presentation: '课程课件',
    manual_wargame_presentation: '兵棋课件',
    lecture_material: '讲课材料',
    rule_verification_matrix: '规则核验矩阵',
    internal_reference: '内部参考'
  } as Record<string, string>)[productType] || productType
}

function documentStatLabel(documentItem: WritingProjectDocument) {
  if (documentItem.kind === 'rich_text') return `${documentItem.stats?.chapter_count || 0} 章`
  if (documentItem.kind === 'workbook') return `${documentItem.stats?.sheet_count || 0} 表 · ${formatNumber(documentItem.stats?.formula_count)} 公式`
  return `${documentItem.stats?.slide_count || 0} 页`
}

function documentOutputSummary(documentItem: WritingProjectDocument) {
  if (documentItem.kind === 'presentation') {
    const documentVersion = documentItem.data_version || `v${documentItem.revision}`
    const structureVersion = documentItem.rules_version || '结构未绑定'
    return `PPT · ${documentVersion} · ${documentItem.stats?.slide_count || 0}页 · ${structureVersion} · ${publicationLabel(documentItem.publication_status)}`
  }
  if (documentItem.kind === 'rich_text') {
    return richTextOutputSummary(
      documentItem,
      publicationLabel(documentItem.publication_status)
    )
  }
  return `${documentKindLabel(documentItem.kind)} · v${documentItem.revision} · ${documentStatLabel(documentItem)}`
}

function structureBindingLabel(status: DocumentStructureBindingStatus) {
  return ({
    aligned: '结构一致',
    diverged: '存在差异',
    stale: '已过期',
    missing: '未绑定'
  } as Record<string, string>)[status] || status
}

function structureBindingTagType(status: DocumentStructureBindingStatus) {
  if (status === 'aligned') return 'success'
  if (status === 'missing') return 'info'
  return 'warning'
}

function documentOrderIndex(documentItem: WritingProjectDocument) {
  return documentCollection.value?.documents.findIndex(row => row.id === documentItem.id) ?? -1
}

function publicationLabel(status: WritingPublicationStatus) {
  return ({
    draft: '草稿',
    review: '核校',
    approved: '已批准',
    published: '已发布',
    internal: '内部'
  } as Record<WritingPublicationStatus, string>)[status] || status
}

function publicationTagType(status: WritingPublicationStatus) {
  if (status === 'published' || status === 'approved') return 'success'
  if (status === 'review') return 'warning'
  return 'info'
}

function projectStatusLabel(status: string) {
  return ({ active: '进行中', planning: '规划中', completed: '已完成', archived: '已归档' } as Record<string, string>)[status] || status
}

function projectStatusType(status: string) {
  if (status === 'active') return 'success'
  if (status === 'planning') return 'warning'
  if (status === 'archived') return 'info'
  return 'primary'
}

async function loadSection(sectionId: string) {
  if (!selectedProjectId.value || !selectedDocumentId.value) return
  sectionLoading.value = true
  try {
    revokeObjectUrls()
    currentSection.value = await getDocumentWritingSection(selectedProjectId.value, selectedDocumentId.value, sectionId)
    displayMarkdown.value = await hydrateAssets(currentSection.value.content || '', currentSection.value.asset_paths || [])
  } catch (error) {
    ElMessage.error(errorMessage(error, '章节加载失败'))
  } finally {
    sectionLoading.value = false
  }
}

async function selectDirectoryNode(node: WritingDirectoryNode) {
  const needsSectionLoad = readerMode.value !== 'section'
    || selectedSectionId.value !== node.section_id
    || currentSection.value?.id !== node.section_id
  readerMode.value = 'section'
  selectedSectionId.value = node.section_id
  selectedDirectoryNodeId.value = node.id
  if (needsSectionLoad) await loadSection(node.section_id)
  await nextTick()
  const target = documentBody.value?.querySelector<HTMLElement>(`#${CSS.escape(node.target_id)}`)
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function findDirectoryNode(
  nodes: WritingDirectoryNode[],
  nodeId: string
): WritingDirectoryNode | undefined {
  for (const node of nodes) {
    if (node.id === nodeId) return node
    const child = findDirectoryNode(node.children || [], nodeId)
    if (child) return child
  }
  return undefined
}

function flattenDirectory(nodes: WritingDirectoryNode[]): WritingDirectoryNode[] {
  return nodes.flatMap(node => [node, ...flattenDirectory(node.children || [])])
}

function outlineNumber(value: string) {
  const numbered = value.match(/(?:第\s*)?(\d+)(?:\s*章|(?:\.\d+){0,2})/)
  return numbered?.[1]
    ? (value.match(/\d+(?:\.\d+){0,2}/)?.[0] || numbered[1])
    : ''
}

function sectionMatchesOutline(section: string, token: string) {
  const normalized = String(section || '').replace(/\s+/g, '')
  if (token.includes('.')) {
    return normalized.split(/[、,，/]/).some(item => item === token || item.startsWith(`${token}.`))
  }
  return normalized.split(/[、,，/]/).some(item => (
    item === token
    || item.startsWith(`${token}.`)
    || item.startsWith(`第${token}章`)
  ))
}

async function navigateFromPresentation(
  payload: { sourceDocumentId: string; section: string },
  preserveStudioMode = false
) {
  await selectDocument(payload.sourceDocumentId, undefined, preserveStudioMode)
  activeView.value = 'reader'
  readerMode.value = 'section'
  const candidates = flattenDirectory(workspace.value?.directory || [])
  const sectionTokens = payload.section
    .split(/[、,，/]/)
    .map(value => value.trim())
    .filter(Boolean)
  let node = candidates.find(item => (
    sectionTokens.some(token => {
      const tokenNumber = outlineNumber(token) || token
      return outlineNumber(item.title) === tokenNumber
        || item.target_id === token
        || item.title.trim().startsWith(`${tokenNumber} `)
    })
  ))
  if (!node) {
    const chapter = sectionTokens[0]?.split('.')[0] || ''
    node = candidates.find(item => (
      outlineNumber(item.title) === chapter
      || item.title.includes(`第${chapter}章`)
    ))
  }
  if (node) await selectDirectoryNode(node)
}

async function navigateFromLinkedPresentation(payload: { sourceDocumentId: string; section: string }) {
  studioMode.value = 'linked'
  await navigateFromPresentation(payload, true)
  studioMode.value = 'linked'
}

async function openPresentationSlide(documentId: string, slide: number) {
  await selectDocument(documentId, slide)
}

async function openSection(section: WritingSection) {
  activeView.value = 'reader'
  selectedSectionId.value = section.id
  selectedDirectoryNodeId.value = section.id
  await loadSection(section.id)
}

async function changeReaderMode() {
  if (readerMode.value === 'full') {
    sectionLoading.value = true
    try {
      revokeObjectUrls()
      const fulltext = await getDocumentWritingFulltext(selectedProjectId.value, selectedDocumentId.value)
      displayMarkdown.value = await hydrateAssets(fulltext.content, fulltext.asset_paths)
    } catch (error) {
      ElMessage.error(errorMessage(error, '全文加载失败'))
    } finally {
      sectionLoading.value = false
    }
  } else if (selectedSectionId.value) {
    selectedDirectoryNodeId.value = selectedSectionId.value
    await loadSection(selectedSectionId.value)
  }
}

async function hydrateAssets(markdown: string, paths: string[]) {
  let hydrated = markdown
  await Promise.all(paths.map(async path => {
    try {
      const blob = await getDocumentWritingAsset(selectedProjectId.value, selectedDocumentId.value, path)
      const url = URL.createObjectURL(blob)
      objectUrls.value.push(url)
      hydrated = hydrated.split(`](${path})`).join(`](${url})`)
    } catch {
      // The quality report exposes missing resources; keep the original path visible in the reader.
    }
  }))
  return hydrated
}

function revokeObjectUrls() {
  objectUrls.value.forEach(url => URL.revokeObjectURL(url))
  objectUrls.value = []
}

async function handleViewChange(name: string | number) {
  if (name === 'graph') await loadGraph()
  if (name === 'references') await loadReferences()
  if (name === 'delivery') await loadDelivery()
}

async function loadGraph() {
  if (!graphData.value) graphData.value = await getDocumentWritingGraph(selectedProjectId.value, selectedDocumentId.value)
  await nextTick()
  renderGraph()
}

function renderGraph() {
  if (!graphElement.value || !graphData.value) return
  graphChart ||= echarts.init(graphElement.value)
  const allowedTypes = graphMode.value === 'concept' ? new Set(['section', 'concept']) : new Set(['section', 'claim'])
  const nodes = graphData.value.nodes.filter(node => allowedTypes.has(node.type))
  const allowedIds = new Set(nodes.map(node => node.id))
  const categories = graphMode.value === 'concept'
    ? [{ name: '章节' }, { name: '概念' }]
    : [{ name: '章节' }, { name: '论点' }]
  graphChart.setOption({
    tooltip: { formatter: (params: any) => params.data.detail || `${params.data.name}<br/>${params.data.type}` },
    legend: { data: categories.map(row => row.name), top: 0, textStyle: { color: '#aeb8c6' } },
    series: [{
      type: 'graph', layout: 'force', roam: true, draggable: true, categories,
      data: nodes.map(node => ({
        ...node,
        category: node.type === 'section' ? 0 : 1,
        symbolSize: node.type === 'section' ? 28 : Math.max(10, Math.min(24, 10 + Math.log2((node.value || 1) + 1) * 3))
      })),
      links: graphData.value.edges.filter(edge => allowedIds.has(edge.source) && allowedIds.has(edge.target)).map(edge => ({ ...edge, name: edge.relation })),
      force: { repulsion: 240, edgeLength: [70, 150], gravity: 0.08 },
      label: { show: true, color: '#d8dee8', fontSize: 10, width: 110, overflow: 'truncate' },
      lineStyle: { opacity: 0.4, color: 'source', curveness: 0.08 },
      emphasis: { focus: 'adjacency' }
    }]
  }, true)
  graphChart.off('click')
  graphChart.on('click', event => {
    if (event.dataType === 'node') selectedGraphNode.value = graphData.value?.nodes.find(node => node.id === (event.data as any).id)
  })
  graphChart.resize()
}

async function loadReferences() {
  if (!references.value) references.value = await getDocumentWritingReferences(selectedProjectId.value, selectedDocumentId.value)
}

async function openReferenceLocation(location: Pick<WritingReferenceCoverage, 'section_id'>) {
  const section = workspace.value?.sections.find(row => row.id === location.section_id)
  if (section) await openSection(section)
}

async function loadDelivery() {
  const [quality, history, layout] = await Promise.all([
    getDocumentWritingQuality(selectedProjectId.value, selectedDocumentId.value),
    getDocumentWritingVersions(selectedProjectId.value, selectedDocumentId.value),
    getDocumentLayout(selectedProjectId.value, selectedDocumentId.value)
  ])
  qualityReport.value = quality
  versions.value = history.versions
  layoutState.value = layout
}

async function saveLayout(payload: { profile_id?: string; layout_revision: string; cover: Record<string, string> }) {
  layoutSaving.value = true
  try {
    layoutState.value = await updateDocumentLayout(selectedProjectId.value, selectedDocumentId.value, payload)
    ElMessage.success('排版模板与封面信息已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error, '排版设置保存失败'))
  } finally {
    layoutSaving.value = false
  }
}

async function previewLayoutSample() {
  try {
    const blob = await getDocumentLayoutSample(selectedProjectId.value, selectedDocumentId.value, 'pdf')
    const url = URL.createObjectURL(blob)
    objectUrls.value.push(url)
    pdfPreviewUrl.value = url
    pdfPreviewVisible.value = true
  } catch (error) {
    ElMessage.error(errorMessage(error, '模板样张预览失败'))
  }
}

async function downloadLayoutDelivery(format: 'docx' | 'pdf') {
  try {
    const blob = await getDocumentLayoutDelivery(selectedProjectId.value, selectedDocumentId.value, format)
    if (format === 'pdf') {
      const url = URL.createObjectURL(blob)
      objectUrls.value.push(url)
      pdfPreviewUrl.value = url
      pdfPreviewVisible.value = true
    } else {
      downloadBlob(blob, `${layoutState.value?.binding.latest_delivery?.docx_path?.split('/').pop() || '当前交付稿.docx'}`)
    }
  } catch (error) {
    ElMessage.error(errorMessage(error, '当前交付稿下载失败'))
  }
}

async function downloadSourceWord() {
  try {
    const blob = await getDocumentWritingSourceWord(selectedProjectId.value, selectedDocumentId.value)
    downloadBlob(blob, `${workspace.value?.project.name || '文档'}-原文.docx`)
  } catch (error) {
    ElMessage.error(errorMessage(error, 'Word 原文下载失败'))
  }
}

async function exportDocument(format: 'docx' | 'pdf') {
  const preflightOk = await runExportPreflight(format)
  if (!preflightOk) return
  exporting.value = format
  try {
    const blob = await exportProjectWritingDocument(selectedProjectId.value, selectedDocumentId.value, format)
    if (format === 'pdf') {
      const url = URL.createObjectURL(blob)
      objectUrls.value.push(url)
      pdfPreviewUrl.value = url
      pdfPreviewVisible.value = true
    } else {
      const basename = layoutState.value?.binding.delivery_basename || `${workspace.value?.project.name || '文档'}-${currentContentVersionLabel.value}`
      downloadBlob(blob, `${basename}.${format}`)
    }
    ElMessage.success(`${format.toUpperCase()} 已生成`)
    await loadDelivery()
  } catch (error) {
    ElMessage.error(errorMessage(error, `${format.toUpperCase()} 生成失败`))
  } finally {
    exporting.value = ''
  }
}

async function runExportPreflight(format: 'docx' | 'pdf') {
  const issues: Array<{ severity: 'blocker' | 'warning'; message: string }> = []
  try {
    if (readerMode.value === 'section' && collaborationEditor.value?.prepareExportPreflight) {
      const editorPreflight = await collaborationEditor.value.prepareExportPreflight()
      issues.push(...editorPreflight.issues)
    }

    const quality = await getDocumentWritingQuality(selectedProjectId.value, selectedDocumentId.value)
    if (quality.summary.blockers > 0) {
      issues.push({ severity: 'blocker', message: `技术完整度存在 ${quality.summary.blockers} 个阻断问题，请先在交付检查中处理。` })
    }
    if (quality.summary.missing_assets > 0) {
      issues.push({ severity: 'blocker', message: `交付检查发现 ${quality.summary.missing_assets} 个缺失图片资源，请补齐后再导出。` })
    }
    if (quality.summary.warnings > 0) {
      issues.push({ severity: 'warning', message: `技术完整度仍有 ${quality.summary.warnings} 条警告，已允许导出但建议复核。` })
    }
  } catch (error) {
    issues.push({ severity: 'blocker', message: errorMessage(error, '导出前检查失败，请刷新后重试。') })
  }

  try {
    const collaboration = await getWritingCollaboration(selectedProjectId.value, selectedDocumentId.value, selectedSectionId.value)
    if (collaboration.projection?.status && collaboration.projection.status !== 'current') {
      issues.push({ severity: 'blocker', message: `Markdown 投影状态为 ${collaboration.projection.status}，请刷新正文或重新保存后再导出。` })
    }
  } catch {
    // 未启用人机双写的旧文档仍可走后端兼容导出。
  }

  const blockers = issues.filter(issue => issue.severity === 'blocker')
  if (blockers.length) {
    await ElMessageBox.alert(blockers.map(issue => `- ${issue.message}`).join('\n'), `${format.toUpperCase()} 导出已暂停`, {
      confirmButtonText: '知道了',
      type: 'warning'
    })
    return false
  }

  const warnings = issues.filter(issue => issue.severity === 'warning')
  if (warnings.length) {
    ElMessage.warning(warnings[0].message)
  }
  return true
}

async function exportFormalPackage() {
  if (isCourseProject.value && productionStatus.value && !productionStatus.value.summary.can_export) {
    productionDialogVisible.value = true
    ElMessage.warning('课程产品尚未通过正式交付检查')
    return
  }
  exportingPackage.value = true
  try {
    const blob = await exportWritingProjectPackage(selectedProjectId.value)
    const projectName = documentCollection.value?.project.name || '文档项目'
    downloadBlob(blob, `${projectName}-正式交付包.zip`)
    ElMessage.success(`正式交付包已生成，共 ${formalDocuments.value.length} 册 Word`)
  } catch (error) {
    ElMessage.error(errorMessage(error, '正式交付包生成失败'))
  } finally {
    exportingPackage.value = false
  }
}

function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function filterReferences(rows: WritingReference[]) {
  const keyword = referenceSearch.value.trim().toLowerCase()
  if (!keyword) return rows
  return rows.filter(row => `${row.number || ''} ${row.title || ''} ${row.text || ''} ${row.year || ''}`.toLowerCase().includes(keyword))
}

function graphNodeTypeLabel(type: string) {
  return ({ section: '文档章节', concept: '知识库概念', claim: '核心论点' } as Record<string, string>)[type] || type
}

function formatNumber(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(value || 0)
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function formatFileSize(value: number) {
  return value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.round(value / 1024)} KB`
}

function errorMessage(error: unknown, fallback: string) {
  const detail = (error as any)?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail.message === 'string') return detail.message
  return fallback
}

function handleResize() {
  graphChart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadWorkspace()
})
onBeforeUnmount(() => {
  clearEvaluationPolling()
  window.removeEventListener('resize', handleResize)
  revokeObjectUrls()
  graphChart?.dispose()
})
</script>

<style scoped>
.writing-page { display: grid; gap: 14px; width: 100%; max-width: 100%; min-width: 0; overflow: hidden; }
.writing-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.writing-head h2, .writing-head p, .section-title h3, .graph-toolbar h3, .reference-toolbar h3 { margin: 0; }
.writing-head h2 { margin-top: 3px; color: var(--text-primary); font-size: 20px; }
.writing-head p { margin-top: 5px; color: var(--text-secondary); font-size: 12px; }
.title-line { display: flex; align-items: center; gap: 8px; }
.eyebrow, .section-title span, .graph-toolbar span, .reference-toolbar span { color: var(--view-color-primary); font-size: 11px; }
.head-actions { display: flex; gap: 8px; }
.document-manager { display: grid; gap: 11px; padding-block: 12px; border-block: 1px solid var(--line-color); }
.manager-head { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.manager-head h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 14px; letter-spacing: 0; }
.manager-head .el-input { width: min(340px, 42vw); }
.document-project-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 10px; }
.document-project-card { position: relative; display: grid; gap: 10px; min-width: 0; padding: 12px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); cursor: pointer; }
.document-project-card:hover, .document-project-card.active { border-color: var(--view-color-primary); background: var(--view-color-faint); }
.document-project-card.archived { opacity: .68; }
.project-card-main { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 9px; padding-right: 62px; }
.document-icon { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 5px; color: var(--view-color-primary); background: var(--view-color-faint); }
.project-name-line { display: flex; align-items: center; gap: 7px; min-width: 0; }
.project-name-line strong { overflow: hidden; color: var(--text-primary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.project-card-main p { display: -webkit-box; margin: 4px 0 0; overflow: hidden; color: var(--text-secondary); font-size: 10px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.project-card-meta { display: flex; flex-wrap: wrap; gap: 5px 10px; color: var(--text-secondary); font-size: 9px; }
.project-card-actions { position: absolute; top: 7px; right: 7px; display: flex; align-items: center; }
.project-card-actions .el-button { width: 26px; height: 26px; margin: 0; }
.project-document-library { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.course-production-panel { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--view-color-border); border-radius: 6px; background: var(--view-color-faint); }
.course-production-panel > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.course-panel-actions { display: flex; align-items: center; gap: 8px; }
.course-production-panel h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 14px; }
.course-baseline-metrics { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); border-block: 1px solid var(--line-color); }
.course-baseline-metrics > div { display: grid; gap: 3px; padding: 8px 10px; border-right: 1px solid var(--line-color); }
.course-baseline-metrics > div:last-child { border-right: 0; }
.course-baseline-metrics span { color: var(--text-secondary); font-size: 10px; }
.course-baseline-metrics strong { color: var(--text-primary); font-size: 15px; }
.course-iteration-bar { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 8px 0; border-bottom: 1px solid var(--line-color); }
.course-iteration-status { display: flex; align-items: center; gap: 18px; min-width: 0; }
.course-iteration-status > span { display: grid; gap: 2px; }
.course-iteration-status small { color: var(--text-secondary); font-size: 9px; }
.course-iteration-status strong { color: var(--text-primary); font-size: 13px; }
.course-iteration-controls { display: flex; align-items: flex-end; gap: 8px; }
.course-iteration-controls label { display: grid; gap: 3px; color: var(--text-secondary); font-size: 9px; }
.course-iteration-controls :deep(.el-input-number) { width: 92px; }
.course-workstream-table { display: grid; border-block: 1px solid var(--line-color); }
.course-workstream-row { display: grid; grid-template-columns: minmax(210px, 1.25fr) minmax(120px, 1fr) 88px 82px; gap: 12px; align-items: center; min-width: 0; padding: 7px 0; border-bottom: 1px solid var(--line-color); }
.course-workstream-row:last-child { border-bottom: 0; }
.course-workstream-row > div:first-child { display: grid; gap: 2px; min-width: 0; }
.course-workstream-row strong { overflow: hidden; color: var(--text-primary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.course-workstream-row small, .course-workstream-row > span { color: var(--text-secondary); font-size: 9px; }
.course-attention-list { display: grid; border-bottom: 1px solid var(--line-color); }
.course-attention-list > header { display: flex; align-items: center; justify-content: space-between; padding: 2px 0 6px; }
.course-attention-list > header strong { color: var(--text-primary); font-size: 11px; }
.course-attention-list > header small { color: var(--text-secondary); font-size: 9px; }
.course-attention-row { display: grid; grid-template-columns: minmax(0, 1fr) 70px minmax(0, auto); gap: 10px; align-items: center; padding: 7px 0; border-top: 1px solid var(--line-color); }
.course-attention-row > div:first-child { display: grid; gap: 2px; min-width: 0; }
.course-attention-row strong { overflow: hidden; color: var(--text-primary); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.course-attention-row small { overflow: hidden; color: var(--text-secondary); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.course-review-actions { display: flex; align-items: center; justify-content: flex-end; gap: 6px; min-width: 0; }
.course-review-actions .el-button { margin: 0; }
.course-blocker-preview { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #e6a23c; font-size: 11px; }
.production-blocker-list { display: grid; gap: 8px; max-height: 58vh; overflow-y: auto; }
.production-blocker-list > div { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px; align-items: start; padding: 8px 0; border-bottom: 1px solid var(--line-color); color: var(--text-primary); font-size: 11px; line-height: 1.5; }
.document-library-head { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.document-library-head h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 13px; }
.document-library-actions { display: flex; align-items: center; gap: 10px; }
.document-groups { display: grid; gap: 10px; }
.document-group { display: grid; gap: 8px; min-width: 0; padding: 10px; border: 1px solid var(--line-color); background: var(--page-bg); }
.document-group > header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.document-group > header > div { display: grid; gap: 2px; }
.document-group > header strong { color: var(--text-primary); font-size: 12px; }
.document-group > header small { color: var(--text-secondary); font-size: 9px; }
.internal-documents { border-style: dashed; }
.project-document-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 8px; }
.project-document-card { display: grid; grid-template-columns: 34px minmax(0, 1fr) auto; gap: 9px; align-items: center; min-width: 0; padding: 10px; border: 1px solid var(--line-color); border-radius: 5px; cursor: pointer; }
.project-document-card:hover, .project-document-card.active { border-color: var(--view-color-primary); background: var(--view-color-faint); }
.project-document-card.internal { background: var(--card-bg); }
.project-document-card.archived { opacity: .64; }
.document-type-icon { display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; color: var(--view-color-primary); background: var(--view-color-faint); }
.document-card-body { display: grid; gap: 4px; min-width: 0; }
.document-card-body > div { display: flex; align-items: center; gap: 6px; min-width: 0; }
.document-card-body strong { overflow: hidden; color: var(--text-primary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.document-card-body small { color: var(--text-secondary); font-size: 9px; }
.document-card-actions { display: flex; align-items: center; }
.document-card-actions .el-button { width: 26px; height: 26px; margin: 0; }
.document-form { display: grid; gap: 14px; }
.project-form { display: grid; gap: 12px; }
.project-form-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.project-form-row.title { grid-template-columns: minmax(0, 1.5fr) minmax(150px, .7fr); }
.form-tip { color: var(--text-secondary); font-size: 10px; }
.status-strip { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); border-block: 1px solid var(--line-color); }
.status-strip > div { display: grid; gap: 3px; padding: 9px 12px; border-right: 1px solid var(--line-color); }
.status-strip > div:last-child { border-right: 0; }
.status-strip span, .brief-grid span, .quality-facts span, .graph-metrics span, .source-grid span { color: var(--text-secondary); font-size: 11px; }
.status-strip strong { color: var(--text-primary); font-size: 17px; }
.status-strip .edition-value { font-size: 14px; }
.content-studio-tabs { min-width: 0; max-width: 100%; padding: 0 12px; border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.content-studio-tabs :deep(.el-tabs__header) { margin: 0; }
.content-studio-tabs :deep(.el-tabs__nav-wrap::after) { height: 1px; background: var(--line-color); }
.content-studio-tabs :deep(.el-tabs__item) { height: 42px; font-size: 12px; }
.content-studio-tabs :deep(.el-tabs__content) { display: none; }
.workspace-tabs { min-width: 0; max-width: 100%; margin-top: -4px; }
.workspace-tabs :deep(.el-tabs__header) { margin: 0; }
.section-title, .graph-toolbar, .reference-toolbar, .reference-columns > section > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-title h3, .graph-toolbar h3, .reference-toolbar h3, .reference-columns h3 { margin-top: 3px; color: var(--text-primary); font-size: 14px; }
.research-brief, .version-evolution, .target-structure, .chapter-progress, .quality-panel, .document-pane, .inspector-pane, .graph-view, .references-view, .delivery-main, .delivery-side > section { border: 1px solid var(--line-color); border-radius: 6px; background: var(--card-bg); }
.research-brief, .version-evolution, .target-structure, .chapter-progress, .quality-panel, .graph-view, .references-view, .delivery-main, .delivery-side > section { padding: 15px; }
.overview-view { display: grid; gap: 14px; }
.brief-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.brief-grid > div { min-width: 0; padding: 11px; background: var(--view-color-faint); }
.brief-grid p { margin: 5px 0 0; overflow-wrap: anywhere; color: var(--text-primary); font-size: 12px; line-height: 1.6; }
.version-evolution { display: grid; gap: 13px; }
.version-timeline { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-top: 1px solid var(--line-color); border-left: 1px solid var(--line-color); }
.version-stage { display: grid; align-content: start; gap: 5px; min-width: 0; padding: 11px; border-right: 1px solid var(--line-color); border-bottom: 1px solid var(--line-color); }
.version-stage span { color: var(--view-color-primary); font-size: 11px; font-weight: 700; }
.version-stage strong { color: var(--text-primary); font-size: 12px; }
.version-stage p { margin: 0; color: var(--text-secondary); font-size: 11px; line-height: 1.55; }
.version-stage small { align-self: end; color: var(--text-secondary); font-size: 10px; }
.version-stage.current { background: var(--view-color-faint); }
.version-stage.target { box-shadow: inset 0 0 0 1px var(--view-color-border); }
.target-structure__head { align-items: center; }
.target-structure__badges { display: flex; gap: 8px; flex-wrap: wrap; }
.target-structure__meta { display: flex; gap: 16px; margin: 8px 0 12px; color: var(--text-secondary); font-size: 11px; flex-wrap: wrap; }
.target-structure__meta span:last-child { min-width: 0; overflow-wrap: anywhere; }
.structure-comparison { display: grid; grid-template-columns: minmax(0, 1.18fr) minmax(360px, .82fr); gap: 14px; align-items: start; }
.structure-comparison.is-single { grid-template-columns: 1fr; }
.target-chapter-list { display: grid; grid-template-columns: minmax(0, 1fr); border-top: 1px solid var(--line-color); }
.target-chapter { min-width: 0; min-height: 59px; padding: 10px 12px; border-bottom: 1px solid var(--line-color); }
.target-chapter summary { display: flex; min-height: 38px; align-items: center; justify-content: space-between; gap: 12px; cursor: pointer; color: var(--text-primary); }
.target-chapter summary strong { min-width: 0; font-size: 12px; }
.target-chapter summary small { color: var(--text-secondary); white-space: nowrap; font-size: 10px; }
.target-chapter ol { display: grid; gap: 4px; margin: 9px 0 0; padding: 9px 0 0; border-top: 1px solid var(--line-color); list-style: none; color: var(--text-secondary); font-size: 10px; }
.target-chapter li { line-height: 1.45; }
.target-chapter li.outline-level-3 { padding-left: 14px; opacity: .78; }
.chapter-progress { display: grid; gap: 0; }
.comparison-hint { min-height: 57px; margin: 8px 0 12px; padding: 8px 10px; color: var(--text-secondary); font-size: 11px; line-height: 1.5; background: var(--view-color-faint); }
.chapter-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px 0; border: 0; border-bottom: 1px solid var(--line-color); color: inherit; text-align: left; background: transparent; cursor: pointer; }
.chapter-row:last-child { border-bottom: 0; }
.chapter-row > div { display: grid; gap: 3px; }
.chapter-row strong { color: var(--text-primary); font-size: 12px; }
.chapter-row small { color: var(--text-secondary); }
.quality-panel { display: grid; grid-template-columns: minmax(210px, .7fr) minmax(0, 2fr) auto; align-items: center; gap: 14px; }
.quality-score { font-size: 28px; }
.quality-facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.quality-facts > div { display: grid; gap: 3px; padding: 9px; background: var(--view-color-faint); }
.quality-good { color: #67c23a !important; }
.quality-warning { color: #e6a23c !important; }
.quality-danger { color: #f56c6c !important; }
.reader-view { display: grid; grid-template-columns: minmax(190px, 250px) minmax(0, 1fr) minmax(230px, 290px); gap: 12px; min-height: calc(100vh - 245px); align-items: stretch; }
.reader-view.is-collaboration { display: block; }
.collaboration-reader { display: grid; gap: 8px; min-width: 0; }
.collaboration-reader__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--text-secondary); font-size: 10px; }
.collaboration-reader__context { display: flex; align-items: center; justify-content: flex-end; gap: 8px; min-width: 0; }
.inspector-pane { padding: 12px; }
.document-pane { min-width: 0; overflow: hidden; }
.document-toolbar { display: flex; align-items: center; justify-content: space-between; padding: 9px 12px; border-bottom: 1px solid var(--line-color); }
.markdown-body { max-height: calc(100vh - 300px); padding: 24px clamp(18px, 4vw, 56px) 56px; overflow: auto; color: var(--text-primary); font-size: 14px; line-height: 1.85; }
.markdown-body :deep(h1) { margin: 1.5em 0 .8em; font-size: 25px; letter-spacing: 0; }
.markdown-body :deep(h2) { margin: 1.45em 0 .65em; padding-bottom: 6px; border-bottom: 1px solid var(--line-color); font-size: 19px; letter-spacing: 0; }
.markdown-body :deep(h3) { margin: 1.3em 0 .55em; font-size: 16px; letter-spacing: 0; }
.markdown-body :deep(h4) { font-size: 14px; letter-spacing: 0; }
.markdown-body :deep(p) { margin: .8em 0; }
.markdown-body :deep(img) { display: block; max-width: 100%; max-height: 620px; margin: 18px auto; object-fit: contain; }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; font-size: 12px; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding: 7px 9px; border: 1px solid var(--line-color); }
.markdown-body :deep(blockquote) { margin: 14px 0; padding: 6px 14px; border-left: 3px solid var(--view-color-primary); color: var(--text-secondary); }
.markdown-editor { padding: 12px; }
.markdown-editor :deep(textarea) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; line-height: 1.65; }
.inspector-pane { min-width: 0; overflow-y: auto; }
.inspector-pane h3 { margin: 4px 0 8px; color: var(--text-primary); font-size: 14px; }
.inspector-pane p { margin: 0 0 12px; color: var(--text-secondary); font-size: 11px; line-height: 1.6; }
.inspector-pane dl { display: grid; margin: 0; }
.inspector-pane dl > div { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--line-color); font-size: 11px; }
.inspector-pane dt { color: var(--text-secondary); }
.inspector-pane dd { margin: 0; color: var(--text-primary); }
.inspector-pane section { margin-top: 15px; padding-top: 12px; border-top: 1px solid var(--line-color); }
.inspector-pane h4 { margin: 0 0 8px; color: var(--text-primary); font-size: 11px; }
.linked-slide-list { display: grid; gap: 6px; }
.linked-slide-list .el-button { justify-content: flex-start; width: 100%; height: auto; margin: 0; padding: 6px 8px; white-space: normal; text-align: left; }
.outline-list { display: grid; gap: 5px; color: var(--text-secondary); font-size: 10px; }
.muted { color: var(--text-secondary); font-size: 11px; }
.graph-view { position: relative; display: grid; gap: 12px; }
.graph-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-block: 1px solid var(--line-color); }
.graph-metrics > div { display: grid; gap: 3px; padding: 8px 10px; border-right: 1px solid var(--line-color); }
.graph-metrics strong { color: var(--text-primary); }
.graph-canvas { width: 100%; height: min(680px, calc(100vh - 330px)); min-height: 480px; }
.graph-selection { position: absolute; right: 24px; bottom: 22px; display: grid; gap: 4px; width: min(330px, 34vw); padding: 12px; border: 1px solid var(--view-color-border); background: var(--panel-bg); }
.graph-selection span { color: var(--view-color-primary); font-size: 10px; }
.graph-selection strong { color: var(--text-primary); font-size: 12px; }
.graph-selection p { margin: 0; color: var(--text-secondary); font-size: 11px; line-height: 1.5; }
.references-view { display: grid; gap: 14px; }
.reference-controls { display: flex; align-items: center; justify-content: flex-end; gap: 8px; min-width: 0; }
.reference-controls .el-input { width: min(300px, 32vw); }
.reference-audit-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border-block: 1px solid var(--line-color); }
.reference-audit-strip > div { display: grid; gap: 3px; padding: 8px 10px; border-right: 1px solid var(--line-color); }
.reference-audit-strip > div:last-child { border-right: 0; }
.reference-audit-strip span { color: var(--text-secondary); font-size: 10px; }
.reference-audit-strip strong { color: var(--text-primary); font-size: 16px; }
.citation-coverage { display: grid; gap: 9px; padding-bottom: 12px; border-bottom: 1px solid var(--line-color); }
.citation-coverage > header { display: flex; align-items: end; justify-content: space-between; gap: 10px; }
.citation-coverage h3 { margin: 3px 0 0; color: var(--text-primary); font-size: 13px; }
.citation-coverage header span, .citation-coverage header small { color: var(--text-secondary); font-size: 10px; }
.coverage-list { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 3px; }
.coverage-list button, .reference-locations button { border: 1px solid var(--view-color-border); border-radius: 4px; color: var(--text-primary); background: var(--view-color-faint); cursor: pointer; }
.coverage-list button { display: grid; flex: 0 0 180px; gap: 3px; padding: 7px 8px; text-align: left; }
.coverage-list button:hover, .reference-locations button:hover { border-color: var(--view-color-primary); }
.coverage-list strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.coverage-list span { color: var(--text-secondary); font-size: 9px; }
.reference-columns { display: grid; grid-template-columns: minmax(260px, .7fr) minmax(0, 1.5fr); gap: 14px; }
.reference-columns > section { min-width: 0; padding: 13px; border: 1px solid var(--line-color); }
.knowledge-reference-list, .formal-reference-list { max-height: calc(100vh - 330px); margin-top: 12px; overflow-y: auto; }
.knowledge-reference-list article { display: grid; gap: 4px; padding: 10px 0; border-bottom: 1px solid var(--line-color); }
.knowledge-reference-list strong, .formal-reference-list strong { color: var(--text-primary); font-size: 11px; line-height: 1.5; }
.knowledge-reference-list small, .formal-reference-list small { color: var(--text-secondary); font-size: 10px; }
.formal-reference-list article { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; gap: 8px; align-items: start; padding: 9px 0; border-bottom: 1px solid var(--line-color); }
.formal-reference-list article > span { color: var(--view-color-primary); font-size: 11px; }
.formal-reference-list article > div { display: grid; gap: 3px; }
.reference-locations { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 3px; }
.reference-locations button { padding: 3px 5px; font-size: 9px; }
.uncited-note { color: #e6a23c !important; }
.delivery-view { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(300px, .75fr); gap: 14px; align-items: start; }
.delivery-main { display: grid; gap: 16px; }
.source-grid { display: grid; gap: 10px; }
.source-grid > div { display: grid; grid-template-columns: 100px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--line-color); }
.source-grid strong { overflow-wrap: anywhere; color: var(--text-primary); font-size: 11px; }
.export-actions { display: flex; gap: 8px; }
.delivery-side { display: grid; gap: 14px; }
.version-list, .issue-list { display: grid; max-height: 280px; margin-top: 10px; overflow-y: auto; }
.version-list > div { display: grid; gap: 3px; padding: 8px 0; border-bottom: 1px solid var(--line-color); }
.version-list strong { color: var(--text-primary); font-size: 11px; }
.version-list small { color: var(--text-secondary); font-size: 10px; }
.issue-list > div { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px; align-items: start; padding: 7px 0; border-bottom: 1px solid var(--line-color); color: var(--text-primary); font-size: 10px; line-height: 1.5; }
.pdf-preview-frame { display: block; width: 100%; height: 78vh; border: 1px solid var(--line-color); background: #fff; }
:deep(.pdf-preview-dialog .el-dialog__body) { padding: 0 14px 14px; }
@media (max-width: 1180px) { .reader-view { grid-template-columns: 210px minmax(0, 1fr); } .inspector-pane { grid-column: 1 / -1; } }
@media (max-width: 1100px) { .course-baseline-metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); } .course-iteration-bar { align-items: stretch; flex-direction: column; } .course-iteration-controls { align-self: flex-end; } .course-workstream-row { grid-template-columns: minmax(190px, 1.2fr) minmax(100px, 1fr) 76px 78px; } }
@media (max-width: 900px) { .status-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); } .version-timeline { grid-template-columns: repeat(2, minmax(0, 1fr)); } .structure-comparison, .reference-columns, .delivery-view { grid-template-columns: 1fr; } .quality-panel { grid-template-columns: 1fr; align-items: stretch; } .quality-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); } .reader-view { grid-template-columns: 1fr; } .markdown-body { max-height: none; } .reference-toolbar { align-items: flex-start; flex-direction: column; } .reference-controls { width: 100%; justify-content: space-between; } .reference-controls .el-input { flex: 1; width: auto; } }
@media (max-width: 640px) { .writing-head, .manager-head, .document-library-head, .course-production-panel > header { align-items: stretch; flex-direction: column; } .head-actions, .manager-head .el-input { width: 100%; } .course-panel-actions { justify-content: space-between; } .course-iteration-status { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; } .course-iteration-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); width: 100%; } .course-iteration-controls :deep(.el-input-number) { width: 100%; } .course-iteration-controls .el-button { grid-column: 1 / -1; width: 100%; } .course-workstream-row { grid-template-columns: minmax(0, 1fr) 78px; } .course-workstream-row > div:first-child { grid-column: 1; grid-row: 1; } .course-workstream-row :deep(.el-progress) { grid-column: 1; grid-row: 2; } .course-workstream-row > span { grid-column: 2; grid-row: 2; justify-self: end; white-space: nowrap; } .course-workstream-row :deep(.el-tag) { grid-column: 2; grid-row: 1; justify-self: end; } .course-attention-row { grid-template-columns: minmax(0, 1fr) auto; } .course-review-actions { grid-column: 1 / -1; justify-content: flex-start; } .document-project-list, .project-document-list, .project-form-row, .project-form-row.title { grid-template-columns: 1fr; } .document-library-actions { justify-content: space-between; flex-wrap: wrap; } .course-baseline-metrics, .status-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } .brief-grid, .version-timeline { grid-template-columns: 1fr; } .graph-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } .reference-controls { align-items: stretch; flex-direction: column; } .reference-controls .el-input { width: 100%; } .reference-audit-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } .reference-audit-strip > div { border-bottom: 1px solid var(--line-color); } .formal-reference-list article { grid-template-columns: 34px minmax(0, 1fr); } .formal-reference-list .el-tag { grid-column: 2; justify-self: start; } .source-grid > div { grid-template-columns: 1fr; } }
</style>
