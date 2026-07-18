<template>
  <section v-loading="loading">
    <div class="toolbar">
      <el-select v-model="projectId" placeholder="选择项目" filterable @change="loadProjectData">
        <el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <el-button type="primary" @click="projectDialog = true">新建项目</el-button>
      <el-button :disabled="!projectId" @click="allocationDialog = true">登记拨付</el-button>
      <el-button :disabled="!projectId" @click="resetBudget(); budgetDialog = true">编制预算</el-button>
    </div>
    <el-row :gutter="16">
      <el-col :xs="24" :lg="9">
        <el-card shadow="never"><template #header><b>经费拨付</b></template>
          <el-table :data="allocations" empty-text="暂无拨付">
            <el-table-column prop="reference_no" label="拨付编号" />
            <el-table-column prop="amount" label="金额"><template #default="{row}">{{ formatMoney(row.amount) }}</template></el-table-column>
            <el-table-column prop="allocated_at" label="日期" width="110" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="15">
        <el-card shadow="never"><template #header><b>预算版本</b></template>
          <el-collapse accordion>
            <el-collapse-item v-for="budget in budgets" :key="budget.id" :name="budget.id">
              <template #title><span class="budget-title">{{ budget.name }} · V{{ budget.version_no }} <el-tag size="small">{{ budget.status }}</el-tag> <b>{{ formatMoney(budget.approved_amount) }}</b></span></template>
              <el-table :data="budget.lines" size="small">
                <el-table-column prop="category" label="科目" />
                <el-table-column label="额度"><template #default="{row}">{{ formatMoney(row.amount) }}</template></el-table-column>
                <el-table-column label="占用"><template #default="{row}">{{ formatMoney(row.reserved_amount) }}</template></el-table-column>
                <el-table-column label="支出"><template #default="{row}">{{ formatMoney(row.spent_amount) }}</template></el-table-column>
                <el-table-column label="可用"><template #default="{row}">{{ formatMoney(Number(row.amount)-Number(row.reserved_amount)-Number(row.spent_amount)) }}</template></el-table-column>
              </el-table>
              <div class="actions" v-if="budget.status === 'draft'">
                <el-button @click="editBudget(budget)">编辑科目</el-button>
                <el-button type="success" @click="approve(budget)">审批预算</el-button>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="projectDialog" title="新建财务项目" width="480px">
      <el-form label-width="90px"><el-form-item label="项目编码"><el-input v-model="projectForm.project_key" /></el-form-item><el-form-item label="项目名称"><el-input v-model="projectForm.name" /></el-form-item></el-form>
      <template #footer><el-button @click="projectDialog=false">取消</el-button><el-button type="primary" @click="createProject">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="allocationDialog" title="登记经费拨付" width="520px">
      <el-form label-width="90px"><el-form-item label="拨付编号"><el-input v-model="allocationForm.reference_no" /></el-form-item><el-form-item label="金额"><el-input-number v-model="allocationForm.amount" :min="0.01" :precision="2" /></el-form-item><el-form-item label="拨付日期"><el-date-picker v-model="allocationForm.allocated_at" value-format="YYYY-MM-DD" /></el-form-item><el-form-item label="来源"><el-input v-model="allocationForm.source" /></el-form-item></el-form>
      <template #footer><el-button @click="allocationDialog=false">取消</el-button><el-button type="primary" @click="createAllocation">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="budgetDialog" title="编制预算" width="700px">
      <el-form label-width="100px"><el-form-item label="预算名称"><el-input v-model="budgetForm.name" /></el-form-item><el-form-item label="批复金额"><el-input-number v-model="budgetForm.approved_amount" :min="0.01" :precision="2" /></el-form-item></el-form>
      <el-table :data="budgetForm.lines" size="small"><el-table-column prop="category" label="科目" /><el-table-column label="额度"><template #default="{row}"><el-input-number v-model="row.amount" :min="0" :precision="2" /></template></el-table-column></el-table>
      <template #footer><el-button @click="budgetDialog=false">取消</el-button><el-button type="primary" @click="saveBudget">保存草稿</el-button></template>
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { financeApi, formatMoney, type BudgetVersion, type FinanceProject, type FundAllocation } from '@/api/finance'
const categories = ['差旅费','设备费','会议费','外协费','管理费','材料费','劳务费','其他']
const loading=ref(false), projectDialog=ref(false), allocationDialog=ref(false), budgetDialog=ref(false), projectId=ref('')
const projects=ref<FinanceProject[]>([]), allocations=ref<FundAllocation[]>([]), budgets=ref<BudgetVersion[]>([])
const projectForm=reactive({project_key:'',name:''})
const allocationForm=reactive({reference_no:'',amount:0,allocated_at:'',source:'',note:''})
const budgetForm=reactive<{id:string;version:number;name:string;approved_amount:number;lines:Array<{category:string;amount:number;note:string}>}>({id:'',version:1,name:'',approved_amount:0,lines:categories.map(category=>({category,amount:0,note:''}))})
async function load(){loading.value=true;try{projects.value=await financeApi.projects();if(!projectId.value&&projects.value.length)projectId.value=projects.value[0].id;await loadProjectData()}finally{loading.value=false}}
async function loadProjectData(){if(!projectId.value){allocations.value=[];budgets.value=[];return} ;[allocations.value,budgets.value]=await Promise.all([financeApi.allocations(projectId.value),financeApi.budgets(projectId.value)])}
async function createProject(){if(!projectForm.project_key||!projectForm.name)return ElMessage.warning('请填写项目编码和名称');const item=await financeApi.createProject(projectForm);projectDialog.value=false;projectId.value=item.id;projectForm.project_key='';projectForm.name='';await load();ElMessage.success('项目已创建')}
async function createAllocation(){await financeApi.createAllocation({...allocationForm,project_id:projectId.value});allocationDialog.value=false;await loadProjectData();ElMessage.success('经费拨付已登记')}
function resetBudget(){budgetForm.id='';budgetForm.version=1;budgetForm.name='';budgetForm.approved_amount=0;budgetForm.lines=categories.map(category=>({category,amount:0,note:''}))}
function editBudget(item:BudgetVersion){budgetForm.id=item.id;budgetForm.version=item.lock_version;budgetForm.name=item.name;budgetForm.approved_amount=Number(item.approved_amount);budgetForm.lines=categories.map(category=>{const line=item.lines.find(row=>row.category===category);return {category,amount:Number(line?.amount||0),note:line?.note||''}});budgetDialog.value=true}
async function saveBudget(){let id=budgetForm.id,version=budgetForm.version;if(!id){const created=await financeApi.createBudget({project_id:projectId.value,name:budgetForm.name,approved_amount:budgetForm.approved_amount});id=created.id;version=created.lock_version}await financeApi.replaceBudgetLines(id,{version,lines:budgetForm.lines});budgetDialog.value=false;resetBudget();await loadProjectData();ElMessage.success('预算草稿已保存')}
async function approve(item:BudgetVersion){await ElMessageBox.confirm('审批后本版本将成为项目有效预算，确认继续？','审批预算',{type:'warning'});await financeApi.approveBudget(item.id,item.lock_version);await loadProjectData();ElMessage.success('预算已审批')}
onMounted(load)
</script>
<style scoped>.toolbar{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap}.toolbar .el-select{width:280px}.budget-title{display:flex;gap:12px;align-items:center;width:100%}.budget-title b{margin-left:auto;margin-right:16px}.actions{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}</style>
