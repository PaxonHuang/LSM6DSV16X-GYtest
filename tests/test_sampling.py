"""Execute the production C read_sample against deterministic SPI responses."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC=Path(__file__).parents[1]/'main/main.c'

def function(source,name,kind="bool"):
    start=source.index('static '+kind+' '+name+'(')
    brace=source.index('{',start);depth=1;end=brace+1
    while depth:
        depth += (source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

class SamplingTests(unittest.TestCase):
    def test_bad_block_and_status_error_are_sticky_without_retry(self):
        prefix=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#define CONFIG_BURST_LEN 12
#define LSM6DSV16X_STATUS_REG 0x1e
#define LSM6DSV16X_OUTX_L_G 0x22
struct ctx { int unused; };
typedef struct { struct ctx ctx; unsigned errors,samples_a,samples_g,dup,snaps;
                 unsigned err_status,err_block,err_plaus; bool parked;
                 int64_t last_read_us; uint8_t last_blk[12]; bool have_last_blk;
               } imu_unit_t;
static int64_t esp_timer_get_time(void){return 0;}
static unsigned s_st_hist[256];
static int block_reads,status_reads,fail_status;
static int lsm6dsv16x_read_reg(struct ctx *ctx,int reg,uint8_t *buf,int n) {
    if(reg==LSM6DSV16X_STATUS_REG) {status_reads++; *buf=3; return fail_status ? -1 : 0;}
    block_reads++;
    for(int i=0;i<n;i++)buf[i]=0;
    if(block_reads>1)buf[11]=0x40; /* a retry would hide the first zero block */
    return 0;
}
static float lsm6dsv16x_from_fs2_to_mg(int16_t x){return x*0.061f;}
static float lsm6dsv16x_from_fs2000_to_mdps(int16_t x){return x*70.f;}
'''
        suffix=r'''
int main(void) {
    imu_unit_t u={0};float a[3]={0},g[3]={0};bool ha=false,hg=false;
    assert(!read_sample(&u,a,g,&ha,&hg));
    assert(block_reads==1 && u.errors==1 && !ha && !hg);
    assert(!read_sample(&u,a,g,&ha,&hg));
    assert(block_reads==1 && status_reads==1); /* first error parks this unit */
    imu_unit_t v={0};fail_status=1;
    assert(!read_sample(&v,a,g,&ha,&hg));assert(v.errors==1);
    puts("sampling fail-stop PASS");return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'test.c').write_text(prefix+function(SRC.read_text(),'read_sample')+suffix)
            subprocess.run(['cc','-std=c11',str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
            result=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()


class DataPathTests(unittest.TestCase):
    def test_separate_accel_and_gyro_ready_events_accumulate(self):
        prefix=r'''
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <math.h>
#define CONFIG_BURST_LEN 12
#define LSM6DSV16X_STATUS_REG 0x1e
#define LSM6DSV16X_OUTX_L_G 0x22
#define pdMS_TO_TICKS(x) (x)
#define vTaskDelay(x) ((void)0)
typedef struct {int ctx;unsigned errors,samples_a,samples_g,dup,snaps;
                unsigned err_status,err_block,err_plaus;bool parked;
                int64_t last_read_us;uint8_t last_blk[12];bool have_last_blk;} imu_unit_t;
static int64_t esp_timer_get_time(void){return 0;}
typedef struct {int passed,failed;} test_ctx_t;
static unsigned s_st_hist[256];static int reads;
static void check(test_ctx_t *t,bool ok,const char *format,...) {if(ok)t->passed++;else t->failed++;}
static int lsm6dsv16x_read_reg(int *ctx,int reg,uint8_t *buf,int n) {
 if(reg==LSM6DSV16X_STATUS_REG) {*buf=reads==0?1:reads==1?2:0;reads++;return 0;}
 for(int i=0;i<n;i++)buf[i]=0;
 buf[6]=100;buf[8]=100;buf[10]=0;buf[11]=0x40;return 0;
}
static float lsm6dsv16x_from_fs2_to_mg(int16_t x){return x*0.061f;}
static float lsm6dsv16x_from_fs2000_to_mdps(int16_t x){return x*70.f;}
'''
        suffix='int main(void){imu_unit_t u={0};test_ctx_t t={0};test_data_path(&u,&t);assert(t.failed==0);assert(reads==2);return 0;}'
        source=SRC.read_text()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'test.c').write_text(prefix+function(source,'read_sample')+function(source,'test_data_path','void')+suffix)
            subprocess.run(['cc','-std=c11',str(p/'test.c'),'-lm','-o',str(p/'test')],check=True,capture_output=True)
            result=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
