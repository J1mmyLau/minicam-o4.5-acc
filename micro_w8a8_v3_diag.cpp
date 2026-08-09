#include <acl/acl.h>
#include <aclnn/aclnn_base.h>
#include <aclnnop/aclnn_util.h>
#include <aclnnop/level2/aclnn_quant_matmul_v3.h>
#include <cstdio>
#include <cstdlib>

int main() {
    setbuf(stderr,NULL);setbuf(stdout,NULL);
    fprintf(stderr,"[0] init\n");
    aclInit(nullptr);aclrtSetDevice(0);
    aclrtStream st;aclrtCreateStream(&st);
    
    int K=4096,N=4096,S=1;
    fprintf(stderr,"[1] alloc buffers\n");
    void*dw,*ds,*da,*d_o;
    aclrtMalloc(&dw,(size_t)K*N,ACL_MEM_MALLOC_HUGE_FIRST);
    aclrtMalloc(&ds,8,ACL_MEM_MALLOC_HUGE_FIRST);
    aclrtMalloc(&da,(size_t)K*S,ACL_MEM_MALLOC_HUGE_FIRST);
    aclrtMalloc(&d_o,(size_t)N*S*2,ACL_MEM_MALLOC_HUGE_FIRST);
    
    fprintf(stderr,"[2] create tensors\n");
    int64_t wsh[]={K,N},wst[]={1,K},wsl=K*N;
    aclTensor*tw=aclCreateTensor(wsh,2,ACL_INT8,wst,0,ACL_FORMAT_ND,&wsl,1,dw);
    int64_t ssh[]={1},sst[]={1},ssl=1;
    aclTensor*ts=aclCreateTensor(ssh,1,ACL_UINT64,sst,0,ACL_FORMAT_ND,&ssl,1,ds);
    int64_t ash[]={K,S},ast[]={1,K},asl=K*S;
    aclTensor*ta=aclCreateTensor(ash,2,ACL_INT8,ast,0,ACL_FORMAT_ND,&asl,1,da);
    int64_t osh[]={N,S},ost[]={1,N},osl=N*S;
    aclTensor*to=aclCreateTensor(osh,2,ACL_FLOAT16,ost,0,ACL_FORMAT_ND,&osl,1,d_o);
    
    fprintf(stderr,"[3] WS query\n");
    uint64_t wsSize=0;aclOpExecutor*exec=nullptr;
    auto ret=aclnnQuantMatmulV3GetWorkspaceSize(tw,ta,ts,nullptr,nullptr,true,false,to,&wsSize,&exec);
    fprintf(stderr,"[3] WS ret=%d wsSize=%lu exec=%p\n",ret,wsSize,(void*)exec);
    if(ret!=0){fprintf(stderr,"FAIL: %s\n",aclGetRecentErrMsg());_Exit(1);}
    
    fprintf(stderr,"[4] alloc ws\n");
    void*ws=nullptr;
    if(wsSize>0)aclrtMalloc(&ws,wsSize,ACL_MEM_MALLOC_HUGE_FIRST);
    
    fprintf(stderr,"[5] kernel execute\n");
    auto exec_ret=aclnnQuantMatmulV3(ws,wsSize,exec,st);
    fprintf(stderr,"[5] exec ret=%d\n",exec_ret);
    
    fprintf(stderr,"[6] sync stream\n");
    aclrtSynchronizeStream(st);
    fprintf(stderr,"[6] sync done\n");
    
    fprintf(stderr,"[7] _Exit\n");
    _Exit(0);
}
