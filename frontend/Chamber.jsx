import React,{useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import gsap from 'gsap';

export default function Chamber({phase,still}){
 const host=useRef(null),sceneRef=useRef(null);const [fallback,setFallback]=useState(false);
 useEffect(()=>{
  const el=host.current;let renderer,raf,resize,observer;let visible=true;const resources=[];
  try{
   renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});
   renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setClearColor(0x000000,0);el.appendChild(renderer.domElement);
   const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(38,1,.1,100);camera.position.set(0,.3,8.2);
   const group=new THREE.Group();scene.add(group);group.rotation.set(.32,-.35,-.28);
   const geometry=new THREE.TorusKnotGeometry(1.34,.28,180,24,2,3);resources.push(geometry);
   const material=new THREE.ShaderMaterial({uniforms:{uTime:{value:0},uColor:{value:new THREE.Color('#d6fca1')}},vertexShader:`varying vec3 vNormal;varying vec3 vPosition;void main(){vNormal=normalize(normalMatrix*normal);vPosition=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,fragmentShader:`precision highp float;uniform float uTime;uniform vec3 uColor;varying vec3 vNormal;varying vec3 vPosition;void main(){vec3 n=normalize(vNormal);float f=pow(1.0-abs(n.z),2.8);float light=max(dot(n,normalize(vec3(-.4,.8,1.))),0.);float stripes=.5+.5*sin(vPosition.y*70.0+vPosition.x*15.0-uTime*.6);vec3 metal=mix(vec3(.12,.18,.16),vec3(.72,.82,.71),pow(light,1.7));metal+=uColor*f*.6;metal*=.85+.15*stripes;float band=pow(.5+.5*sin(vPosition.y*2.0-uTime*.35),14.);gl_FragColor=vec4(metal+uColor*band*.12,1.);}`});resources.push(material);
   const knot=new THREE.Mesh(geometry,material);group.add(knot);
   const shellG=new THREE.TorusKnotGeometry(1.34,.305,112,12,2,3);const shellM=new THREE.MeshBasicMaterial({color:0xc0ef8a,wireframe:true,transparent:true,opacity:.055});resources.push(shellG,shellM);group.add(new THREE.Mesh(shellG,shellM));
   const orbitG=new THREE.TorusGeometry(2.45,.012,8,160),orbitM=new THREE.MeshBasicMaterial({color:0x829b78,transparent:true,opacity:.46});resources.push(orbitG,orbitM);
   const orbit1=new THREE.Mesh(orbitG,orbitM);orbit1.rotation.x=1.15;orbit1.rotation.y=.35;group.add(orbit1);
   const orbit2=new THREE.Mesh(orbitG,orbitM);orbit2.rotation.x=-.82;orbit2.rotation.y=.68;group.add(orbit2);
   const dotG=new THREE.SphereGeometry(.065,12,12),dotM=new THREE.MeshBasicMaterial({color:0xdcffae});resources.push(dotG,dotM);
   const dots=[0,1,2].map(()=>{const d=new THREE.Mesh(dotG,dotM);group.add(d);return d});
   const p=new Float32Array(180*3);for(let i=0;i<p.length;i++)p[i]=(Math.sin(i*78.13)*43758.5453%1)*6;
   const pointsG=new THREE.BufferGeometry();pointsG.setAttribute('position',new THREE.BufferAttribute(p,3));const pointsM=new THREE.PointsMaterial({size:.014,color:0x819078,transparent:true,opacity:.55});resources.push(pointsG,pointsM);scene.add(new THREE.Points(pointsG,pointsM));
   const controls={speed:1,rotation:0};sceneRef.current={material,controls,group};
   resize=()=>{const {width,height}=el.getBoundingClientRect();renderer.setSize(width,height,false);camera.aspect=width/Math.max(height,1);camera.updateProjectionMatrix();renderer.render(scene,camera)};
   const ro=new ResizeObserver(resize);ro.observe(el);resize();
   let last=0,t=0;const draw=(now)=>{raf=requestAnimationFrame(draw);if(!visible||document.hidden||now-last<32)return;const delta=Math.min((now-last)/1000,.05);last=now;if(!still)t+=delta*controls.speed;material.uniforms.uTime.value=t;group.rotation.y=-.35+(still?0:Math.sin(t*.12)*.28)+controls.rotation;group.rotation.z=-.28+(still?0:Math.sin(t*.1)*.07);dots.forEach((d,i)=>{const a=t*.18+i*Math.PI*2/3;d.position.set(Math.cos(a)*2.44,Math.sin(a)*1.0,Math.sin(a)*2.2)});renderer.render(scene,camera)};raf=requestAnimationFrame(draw);
   const move=e=>{if(still)return;const rect=el.getBoundingClientRect();gsap.to(controls,{rotation:((e.clientX-rect.left)/rect.width-.5)*.3,duration:1.2,overwrite:true})};
   el.addEventListener('pointermove',move);const reset=()=>gsap.to(controls,{rotation:0,duration:1.2,overwrite:true});el.addEventListener('pointerleave',reset);
   observer=new IntersectionObserver(entries=>visible=entries[0].isIntersecting);observer.observe(el);
   const lost=e=>{e.preventDefault();setFallback(true)};renderer.domElement.addEventListener('webglcontextlost',lost);
   return()=>{cancelAnimationFrame(raf);ro.disconnect();observer.disconnect();el.removeEventListener('pointermove',move);el.removeEventListener('pointerleave',reset);gsap.killTweensOf(controls);resources.forEach(r=>r.dispose());renderer.dispose();renderer.domElement.remove();sceneRef.current=null};
  }catch(e){renderer?.dispose();setFallback(true)}
 },[still]);
 useEffect(()=>{const v=sceneRef.current;if(!v)return;const color=new THREE.Color(phase==='running'?'#d5e9ff':phase==='rejected'||phase==='failed'?'#ffb29b':'#d6fca1');const tween=gsap.to(v.material.uniforms.uColor.value,{r:color.r,g:color.g,b:color.b,duration:still?0:1.3});const speed=gsap.to(v.controls,{speed:phase==='running'?2.5:1,duration:still?0:1});return()=>{tween.kill();speed.kill()}},[phase,still]);
 return <div className="chamber" aria-hidden="true"><div className="chamber-grid"/><div ref={host} className="canvas-host" style={{opacity:fallback?0:1}}/>{fallback&&<div className="fallback-orbit"><i/><i/><i/></div>}<div className="scene-cross top">+</div><div className="scene-cross bottom">+</div><div className="scene-label label-one"><span className="small-square"/>OBSERVE</div><div className="scene-label label-two"><span className="small-square"/>RECOVER</div><div className="scene-coordinate">RG / FIELD 001<br/>CONCEPTUAL VISUAL</div><div className="scene-caption">{phase==='running'?'EXECUTION IN PROGRESS':phase==='complete'?'EXECUTION COMPLETE':'AWAITING INPUT'}<span>∿</span></div></div>
}
