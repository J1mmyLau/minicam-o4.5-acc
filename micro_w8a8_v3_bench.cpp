#include <acl/acl.h>
#include <aclnn/aclnn_base.h>
#include <aclnnop/aclnn_util.h>
#include <aclnnop/level2/aclnn_quant_matmul_v3.h>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <vector>
#include <algorithm>
#include <chrono>

double median(std::vector<double>& v) {
    if(v.empty())return 0;
    std::sort(v.begin(),v.end());
    return v.size()%2?v[v.size()/2]:(v[v.size()/2-1]+v[v.size()/2])/2.0;
}
double mean(const std::vector<double>& v) {
    if(v.empty())return 0;double s=0;for(auto x:v)s+=x;return s/v.size();
}
double p90(std::vector<double>& v){if(v.empty())return 0;auto s=v;std::sort(s.begin(),s.end());return s[(size_t)(s.size()*0.90)];}

int main() {
    setbuf(stderr,NULL);setbuf(stdout,NULL);
    int n_iter=200, S=1;
    int shapes[][2]={{4096,4096},{4096,14336},{14336,4096},{4096,8192},{4096,18432}};
    const char*names[]={"Q/K/V/O","FFN_up","FFN_down","Q+K","QKV+FFN"};

    aclInit(nullptr);aclrtSetDevice(0);
    aclrtStream st;aclrtCreateStream(&st);

    printf("%-12s %8s %8s %10s %10s %10s %10s %8s\n",
           "Layer","K","N","p50_us","mean_us","p90_us","GFLOPS","n");
    printf("%s\n","--------------------------------------------------------------");

    for(int si=0;si<5;si++){
        int K=shapes[si][0],N=shapes[si][1];
        void*dw,*ds,*da,*d_o;
        aclrtMalloc(&dw,(size_t)K*N,ACL_MEM_MALLOC_HUGE_FIRST);
        aclrtMalloc(&ds,8,ACL_MEM_MALLOC_HUGE_FIRST);
        aclrtMalloc(&da,(size_t)K*S,ACL_MEM_MALLOC_HUGE_FIRST);
        aclrtMalloc(&d_o,(size_t)N*S*2,ACL_MEM_MALLOC_HUGE_FIRST);

        int64_t wsh[]={K,N},wst[]={1,K},wsl=K*N;
        aclTensor*tw=aclCreateTensor(wsh,2,ACL_INT8,wst,0,ACL_FORMAT_ND,&wsl,1,dw);
        int64_t ssh[]={1},sst[]={1},ssl=1;
        aclTensor*ts=aclCreateTensor(ssh,1,ACL_UINT64,sst,0,ACL_FORMAT_ND,&ssl,1,ds);
        int64_t ash[]={K,S},ast[]={1,K},asl=K*S;
        aclTensor*ta=aclCreateTensor(ash,2,ACL_INT8,ast,0,ACL_FORMAT_ND,&asl,1,da);
        int64_t osh[]={N,S},ost[]={1,N},osl=N*S;
        aclTensor*to=aclCreateTensor(osh,2,ACL_FLOAT16,ost,0,ACL_FORMAT_ND,&osl,1,d_o);

        std::vector<double> us;us.reserve(n_iter);
        for(int i=0;i<n_iter;i++){
            aclrtSynchronizeStream(st);
            auto t0=std::chrono::steady_clock::now();
            uint64_t wsSize=0;aclOpExecutor*exec=nullptr;
            aclnnQuantMatmulV3GetWorkspaceSize(tw,ta,ts,nullptr,nullptr,true,false,to,&wsSize,&exec);
            void*ws=nullptr;
            if(wsSize>0)aclrtMalloc(&ws,wsSize,ACL_MEM_MALLOC_HUGE_FIRST);
            aclnnQuantMatmulV3(ws,wsSize,exec,st);
            aclrtSynchronizeStream(st);
            if(wsSize>0)aclrtFree(ws);
            auto t1=std::chrono::steady_clock::now();
            us.push_back(std::chrono::duration_cast<std::chrono::microseconds>(t1-t0).count());
        }
        double p50v=median(us),meanv=mean(us),p90v=p90(us);
        double gflops=(2.0*K*N*S)/(p50v*1e3);
        printf("%-12s %8d %8d %10.1f %10.1f %10.1f %10.1f %8zu\n",
               names[si],K,N,p50v,meanv,p90v,gflops,us.size());
    }
    aclrtSynchronizeStream(st);
    _Exit(0);
}
