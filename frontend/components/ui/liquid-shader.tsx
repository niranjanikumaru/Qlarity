import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

export interface InteractiveNebulaShaderProps {
  hasActiveReminders?: boolean;
  hasUpcomingReminders?: boolean;
  disableCenterDimming?: boolean;
  className?: string;
}

/** User-supplied ray-marched nebula, adapted for React 19 and local deployment.
 * Reminder props are retained as palette controls; the landing page sets both false.
 * This is decorative artwork, not an execution or quantum-state visualization.
 */
export function InteractiveNebulaShader({
  hasActiveReminders = false,
  hasUpcomingReminders = false,
  disableCenterDimming = false,
  className = '',
}: InteractiveNebulaShaderProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const materialRef = useRef<THREE.ShaderMaterial | null>(null);
  useEffect(() => {
    const mat = materialRef.current;
    if (mat) {
      mat.uniforms.hasActiveReminders.value = hasActiveReminders;
      mat.uniforms.hasUpcomingReminders.value = hasUpcomingReminders;
      mat.uniforms.disableCenterDimming.value = disableCenterDimming;
    }
  }, [hasActiveReminders, hasUpcomingReminders, disableCenterDimming]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false, powerPreference: 'low-power' }); }
    catch { container.dataset.fallback = 'true'; return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const vertexShader = `varying vec2 vUv;
      void main() { vUv = uv; gl_Position = vec4(position, 1.0); }`;
    const fragmentShader = `
      precision mediump float;
      uniform vec2 iResolution;
      uniform float iTime;
      uniform vec2 iMouse;
      uniform bool hasActiveReminders;
      uniform bool hasUpcomingReminders;
      uniform bool disableCenterDimming;
      varying vec2 vUv;
      #define t iTime
      mat2 m(float a){ float c=cos(a), s=sin(a); return mat2(c,-s,s,c); }
      float map(vec3 p){
        p.xz *= m(t*0.4);
        p.xy *= m(t*0.3);
        vec3 q = p*2. + t;
        return length(p + vec3(sin(t*0.7))) * log(length(p)+1.0)
             + sin(q.x + sin(q.z + sin(q.y))) * 0.5 - 1.0;
      }
      void mainImage(out vec4 O, in vec2 fragCoord) {
        vec2 uv = (fragCoord - iResolution * .5) / min(iResolution.x, iResolution.y);
        uv += (iMouse / iResolution - .5) * .06;
        vec3 col = vec3(0.0);
        float d = 2.5;
        for (int i = 0; i <= 5; i++) {
          vec3 p = vec3(0,0,5.) + normalize(vec3(uv, -1.)) * d;
          float rz = map(p);
          float f = clamp((rz - map(p + 0.1)) * 0.5, -0.1, 1.0);
          vec3 base = hasActiveReminders
            ? vec3(0.05,0.2,0.5) + vec3(4.0,2.0,5.0)*f
            : hasUpcomingReminders
            ? vec3(0.05,0.3,0.1) + vec3(2.0,5.0,1.0)*f
            : vec3(0.1,0.3,0.4) + vec3(5.0,2.5,3.0)*f;
          col = col * base + (1.0 - smoothstep(0.0, 2.5, rz)) * 0.7 * base;
          d += min(rz, 1.0);
        }
        float dist = distance(fragCoord, iResolution*.5);
        float radius = min(iResolution.x, iResolution.y)*.5;
        float dim = disableCenterDimming ? 1.0 : smoothstep(radius*.3, radius*.5, dist);
        O = vec4(col, 1.0);
        if (!disableCenterDimming) O.rgb = mix(O.rgb*.3, O.rgb, dim);
      }
      void main() { mainImage(gl_FragColor, vUv*iResolution); }
    `;
    const uniforms = {
      iTime: { value: 0 },
      iResolution: { value: new THREE.Vector2(1, 1) },
      iMouse: { value: new THREE.Vector2() },
      hasActiveReminders: { value: hasActiveReminders },
      hasUpcomingReminders: { value: hasUpcomingReminders },
      disableCenterDimming: { value: disableCenterDimming },
    };
    const material = new THREE.ShaderMaterial({ vertexShader, fragmentShader, uniforms });
    materialRef.current = material;
    const geometry = new THREE.PlaneGeometry(2, 2);
    scene.add(new THREE.Mesh(geometry, material));
    const preference = matchMedia('(prefers-reduced-motion: reduce)');
    let reduced = preference.matches, paused = false, time = 0, last = 0;
    const draw = () => { if (!paused) renderer.render(scene, camera); };
    const onResize = () => {
      const w = Math.max(1, container.clientWidth), h = Math.max(1, container.clientHeight);
      renderer.setSize(w, h);
      uniforms.iResolution.value.set(w, h);
      uniforms.iMouse.value.set(w/2, h/2);
      draw();
    };
    const onMouseMove = (e: PointerEvent) => {
      if (reduced) return;
      const rect = container.getBoundingClientRect();
      uniforms.iMouse.value.set(e.clientX-rect.left, rect.height-(e.clientY-rect.top));
    };
    const preferenceChange = () => { reduced = preference.matches; last = 0; draw(); };
    const onVisibility = () => { last = 0; };
    const onKey = (event: KeyboardEvent) => { if(event.key === 'Escape') { paused = !paused; last = 0; } };
    const onLost = (event: Event) => { event.preventDefault(); paused = true; renderer.domElement.style.display = 'none'; container.dataset.fallback = 'true'; };
    const observer = new ResizeObserver(onResize); observer.observe(container);
    window.addEventListener('pointermove', onMouseMove);
    window.addEventListener('keydown', onKey);
    document.addEventListener('visibilitychange', onVisibility);
    preference.addEventListener('change', preferenceChange);
    renderer.domElement.addEventListener('webglcontextlost', onLost);
    onResize();
    renderer.setAnimationLoop((now) => {
      if (document.hidden || reduced || paused) { last = 0; return; }
      if (last && now-last < 33) return;
      if (last) time += Math.min((now-last)/1000, .05);
      last = now; uniforms.iTime.value = time; draw();
    });
    return () => {
      observer.disconnect();
      window.removeEventListener('pointermove', onMouseMove);
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('visibilitychange', onVisibility);
      preference.removeEventListener('change', preferenceChange);
      renderer.domElement.removeEventListener('webglcontextlost', onLost);
      renderer.setAnimationLoop(null);
      renderer.domElement.remove();
      materialRef.current = null;
      material.dispose(); geometry.dispose(); renderer.dispose();
    };
  }, []);
  return <div ref={containerRef} className={`fixed inset-0 bg-background nebula-background ${className}`} aria-hidden="true" />;
}
export default InteractiveNebulaShader;
