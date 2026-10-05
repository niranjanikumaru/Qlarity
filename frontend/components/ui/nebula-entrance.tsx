import React from 'react';
import { ArrowUpRight, Play } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import InteractiveNebulaShader from '@/components/ui/liquid-shader';
export function NebulaEntrance({onEnter,onHowItWorks}:{onEnter:()=>void;onHowItWorks:()=>void}) {
  const reduced = useReducedMotion();
  return <main className="nebula-entrance relative isolate flex h-dvh w-full items-center justify-center overflow-hidden" aria-label="RetryGuard entrance">
    <InteractiveNebulaShader hasActiveReminders={false} hasUpcomingReminders={false} disableCenterDimming={false}/>
    <div className="nebula-vignette" aria-hidden="true"/>
    <motion.div className="entrance-actions relative z-10 flex items-center gap-4" initial={{opacity:0,y:reduced?0:12}} animate={{opacity:1,y:0}} transition={{duration:reduced?0:.75,delay:reduced?0:.15}}>
      <button className="entrance-button entrance-primary" onClick={onEnter}>Enter workspace <ArrowUpRight size={18} strokeWidth={1.5}/></button>
      <button className="entrance-button entrance-secondary" onClick={onHowItWorks}><Play size={14} strokeWidth={1.5}/> How it works</button>
    </motion.div>
  </main>;
}
