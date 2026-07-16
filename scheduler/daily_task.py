# -*- coding: utf-8 -*-
"""
每日定时任务调度器
支持 Windows 计划任务配置脚本
"""
import os
import sys
from datetime import datetime, timedelta
from utils.logger import logger


class DailyTaskScheduler:
    """每日任务调度管理"""
    
    def __init__(self, run_time: str = "09:00"):
        self.run_time = run_time
        self.project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.python_exe = sys.executable
        self.main_script = os.path.join(self.project_dir, "main.py")
    
    def create_windows_task(self):
        """
        创建 Windows 计划任务
        需要管理员权限运行
        """
        import subprocess
        
        task_name = "SocialMediaMarketing_Daily"
        run_time = self.run_time.replace(":", "")
        
        # 构建 schtasks 命令
        cmd = [
            "schtasks", "/create",
            "/tn", task_name,
            "/tr", f'"{self.python_exe}" "{self.main_script}"',
            "/sc", "daily",
            "/st", self.run_time,
            "/f"  # 强制覆盖
        ]
        
        logger.info(f"[调度] 创建 Windows 计划任务: {task_name}")
        logger.info(f"[调度] 执行时间: 每日 {self.run_time}")
        logger.info(f"[调度] 命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
            if result.returncode == 0:
                logger.info(f"[调度] 计划任务创建成功 ✅")
                logger.info(f"[调度] 查看任务: schtasks /query /tn {task_name}")
                logger.info(f"[调度] 删除任务: schtasks /delete /tn {task_name} /f")
                return True
            else:
                logger.error(f"[调度] 创建失败: {result.stderr}")
                logger.error("[调度] 请尝试以管理员身份运行此脚本")
                return False
        except Exception as e:
            logger.error(f"[调度] 异常: {e}")
            return False
    
    def run_now(self):
        """立即执行一次"""
        logger.info("[调度] 立即执行任务...")
        import subprocess
        result = subprocess.run([self.python_exe, self.main_script], 
                               capture_output=True, text=True)
        logger.info(f"[调度] 执行完成，返回码: {result.returncode}")
        return result.returncode == 0


def main():
    """调度器入口"""
    import argparse
    parser = argparse.ArgumentParser(description="定时任务调度器")
    parser.add_argument("--create-task", action="store_true", help="创建 Windows 计划任务")
    parser.add_argument("--run-now", action="store_true", help="立即执行一次")
    parser.add_argument("--time", type=str, default="09:00", help="每日执行时间 (HH:MM)")
    args = parser.parse_args()
    
    scheduler = DailyTaskScheduler(run_time=args.time)
    
    if args.create_task:
        scheduler.create_windows_task()
    elif args.run_now:
        scheduler.run_now()
    else:
        print("用法:")
        print("  python scheduler/daily_task.py --create-task     # 创建每日定时任务")
        print("  python scheduler/daily_task.py --run-now         # 立即执行一次")
        print("  python scheduler/daily_task.py --time 10:00       # 指定执行时间")


if __name__ == "__main__":
    main()
