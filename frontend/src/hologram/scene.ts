import * as THREE from 'three';

import { PerfGuard, TIERS, initialTierIndex, type QualityTier } from './quality';
import {
  orbFragmentShader,
  orbVertexShader,
  particleFragmentShader,
  particleVertexShader,
  ringFragmentShader,
  ringVertexShader,
} from './shaders';
import type { AssistantState, HologramSignals } from './signals';

interface StateLook {
  core: THREE.Color;
  edge: THREE.Color;
  amplitude: number;
  spin: number;
  scan: number;
}

const LOOKS: Record<AssistantState, StateLook> = {
  idle: {
    core: new THREE.Color('#062b3a'),
    edge: new THREE.Color('#37d7ff'),
    amplitude: 0.055,
    spin: 0.05,
    scan: 0.03,
  },
  listening: {
    core: new THREE.Color('#053043'),
    edge: new THREE.Color('#4dfbe0'),
    amplitude: 0.14,
    spin: 0.16,
    scan: 0.06,
  },
  thinking: {
    core: new THREE.Color('#2b1704'),
    edge: new THREE.Color('#ffb454'),
    amplitude: 0.1,
    spin: 0.42,
    scan: 0.05,
  },
  speaking: {
    core: new THREE.Color('#07384a'),
    edge: new THREE.Color('#8ef4ff'),
    amplitude: 0.2,
    spin: 0.22,
    scan: 0.09,
  },
};

const MAX_DELTA = 1 / 20;

/**
 * The hologram renderer.
 *
 * Everything expensive (geometry, materials) is allocated once per quality tier;
 * the animation loop only mutates uniforms and lerps colours, and it throttles
 * itself down a tier whenever the measured frame rate drops.
 */
export class HologramScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.PerspectiveCamera;
  private readonly clock = new THREE.Clock();
  private readonly guard = new PerfGuard();
  private readonly resizeObserver: ResizeObserver;

  private orb: THREE.Mesh<THREE.IcosahedronGeometry, THREE.ShaderMaterial> | null = null;
  private particles: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial> | null = null;
  private readonly rings: THREE.Mesh<THREE.RingGeometry, THREE.ShaderMaterial>[] = [];
  private readonly group = new THREE.Group();

  private tierIndex = initialTierIndex();
  private frameHandle = 0;
  private reportedFps = 0;
  private running = false;
  private time = 0;
  private level = 0;
  private readonly core = LOOKS.idle.core.clone();
  private readonly edge = LOOKS.idle.edge.clone();
  private amplitude = LOOKS.idle.amplitude;
  private spin = LOOKS.idle.spin;
  private scan = LOOKS.idle.scan;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly signals: HologramSignals,
    private readonly onFps?: (fps: number, tier: QualityTier['name']) => void,
  ) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: false,
      alpha: true,
      powerPreference: 'high-performance',
      stencil: false,
      depth: true,
    });
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.toneMapping = THREE.NoToneMapping;

    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 40);
    this.camera.position.set(0, 0.35, 4.4);
    this.camera.lookAt(0, 0, 0);
    this.scene.add(this.group);

    this.buildRings();
    this.applyTier();
    this.resize();

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement ?? canvas);
    document.addEventListener('visibilitychange', this.onVisibility);
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.clock.start();
    this.loop();
  }

  stop(): void {
    this.running = false;
    cancelAnimationFrame(this.frameHandle);
  }

  dispose(): void {
    this.stop();
    document.removeEventListener('visibilitychange', this.onVisibility);
    this.resizeObserver.disconnect();
    this.disposeTier();
    for (const ring of this.rings) {
      ring.geometry.dispose();
      ring.material.dispose();
      this.group.remove(ring);
    }
    this.rings.length = 0;
    this.renderer.dispose();
  }

  private get tier(): QualityTier {
    return TIERS[this.tierIndex] ?? TIERS[TIERS.length - 1]!;
  }

  private readonly onVisibility = (): void => {
    if (document.hidden) {
      this.stop();
    } else {
      this.start();
    }
  };

  private buildRings(): void {
    const specs = [
      { inner: 1.35, outer: 1.42, tilt: Math.PI / 2.1, spin: 0.08, ticks: 26, opacity: 0.85 },
      { inner: 1.62, outer: 1.66, tilt: Math.PI / 1.75, spin: -0.05, ticks: 60, opacity: 0.55 },
      { inner: 1.95, outer: 2.02, tilt: Math.PI / 2.6, spin: 0.03, ticks: 12, opacity: 0.4 },
    ];
    for (const spec of specs) {
      const geometry = new THREE.RingGeometry(spec.inner, spec.outer, 220, 1);
      const material = new THREE.ShaderMaterial({
        vertexShader: ringVertexShader,
        fragmentShader: ringFragmentShader,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
        uniforms: {
          uTime: { value: 0 },
          uLevel: { value: 0 },
          uWobble: { value: 0.05 },
          uColor: { value: this.edge },
          uOpacity: { value: spec.opacity },
          uSpin: { value: spec.spin },
          uTicks: { value: spec.ticks },
        },
      });
      const ring = new THREE.Mesh(geometry, material);
      ring.rotation.x = spec.tilt;
      ring.rotation.z = spec.spin * 6;
      this.group.add(ring);
      this.rings.push(ring);
    }
  }

  private applyTier(): void {
    this.disposeTier();
    const tier = this.tier;

    const orbGeometry = new THREE.IcosahedronGeometry(1, tier.detail);
    const orbMaterial = new THREE.ShaderMaterial({
      vertexShader: orbVertexShader,
      fragmentShader: orbFragmentShader,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uAmplitude: { value: this.amplitude },
        uLevel: { value: 0 },
        uDetail: { value: tier.detail >= 5 ? 1.4 : 0.6 },
        uCoreColor: { value: this.core },
        uEdgeColor: { value: this.edge },
        uOpacity: { value: 0.95 },
        uScan: { value: this.scan },
      },
    });
    this.orb = new THREE.Mesh(orbGeometry, orbMaterial);
    this.group.add(this.orb);

    this.particles = this.buildParticles(tier.particles);
    this.group.add(this.particles);

    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, tier.maxPixelRatio));
  }

  private buildParticles(count: number): THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial> {
    const positions = new Float32Array(count * 3);
    const seeds = new Float32Array(count);
    const radii = new Float32Array(count);

    for (let i = 0; i < count; i += 1) {
      const radius = 1.25 + Math.random() * 1.15;
      const angle = Math.random() * Math.PI * 2;
      const height = (Math.random() - 0.5) * 1.5;
      positions[i * 3] = Math.cos(angle) * radius;
      positions[i * 3 + 1] = height;
      positions[i * 3 + 2] = Math.sin(angle) * radius;
      seeds[i] = Math.random();
      radii[i] = radius;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1));
    geometry.setAttribute('aRadius', new THREE.BufferAttribute(radii, 1));

    const material = new THREE.ShaderMaterial({
      vertexShader: particleVertexShader,
      fragmentShader: particleFragmentShader,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uLevel: { value: 0 },
        uSize: { value: 1.6 },
        uPixelRatio: { value: this.renderer.getPixelRatio() },
        uColor: { value: this.edge },
        uOpacity: { value: 0.7 },
      },
    });
    return new THREE.Points(geometry, material);
  }

  private disposeTier(): void {
    if (this.orb) {
      this.group.remove(this.orb);
      this.orb.geometry.dispose();
      this.orb.material.dispose();
      this.orb = null;
    }
    if (this.particles) {
      this.group.remove(this.particles);
      this.particles.geometry.dispose();
      this.particles.material.dispose();
      this.particles = null;
    }
  }

  private resize(): void {
    const parent = this.canvas.parentElement;
    const width = parent?.clientWidth || window.innerWidth;
    const height = parent?.clientHeight || window.innerHeight;
    this.camera.aspect = width / Math.max(height, 1);
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
    if (this.particles) {
      this.particles.material.uniforms.uPixelRatio!.value = this.renderer.getPixelRatio();
    }
  }

  private readonly loop = (): void => {
    if (!this.running) return;
    this.frameHandle = requestAnimationFrame(this.loop);

    const delta = Math.min(this.clock.getDelta(), MAX_DELTA);
    this.time += delta;
    this.update(delta);
    this.renderer.render(this.scene, this.camera);

    const verdict = this.guard.sample(delta);
    if (verdict !== 0) this.retune(verdict);
    // Reported at most once per measurement window, never per frame: pushing this
    // into React state every frame would itself cost frames.
    const fps = Math.round(this.guard.currentFps);
    if (fps !== this.reportedFps) {
      this.reportedFps = fps;
      this.onFps?.(fps, this.tier.name);
    }
  };

  private retune(verdict: -1 | 1): void {
    const next = Math.min(Math.max(this.tierIndex - verdict, 0), TIERS.length - 1);
    if (next === this.tierIndex) return;
    this.tierIndex = next;
    this.applyTier();
    this.resize();
  }

  private update(delta: number): void {
    const look = LOOKS[this.signals.state];
    const smoothing = 1 - Math.exp(-delta * 4.5);

    this.core.lerp(look.core, smoothing);
    this.edge.lerp(look.edge, smoothing);
    this.amplitude += (look.amplitude - this.amplitude) * smoothing;
    this.spin += (look.spin - this.spin) * smoothing;
    this.scan += (look.scan - this.scan) * smoothing;

    const target = Math.min(this.signals.level + this.signals.activity * 0.5, 1);
    this.level += (target - this.level) * (1 - Math.exp(-delta * 9));
    this.signals.activity *= Math.exp(-delta * 2.2);

    this.group.rotation.y += delta * (0.12 + this.spin);
    this.group.rotation.x = Math.sin(this.time * 0.18) * 0.06;

    if (this.orb) {
      const uniforms = this.orb.material.uniforms;
      uniforms.uTime!.value = this.time;
      uniforms.uAmplitude!.value = this.amplitude;
      uniforms.uLevel!.value = this.level;
      uniforms.uScan!.value = this.scan;
      const scale = 1 + this.level * 0.06;
      this.orb.scale.setScalar(scale);
    }

    for (const ring of this.rings) {
      const uniforms = ring.material.uniforms;
      uniforms.uTime!.value = this.time;
      uniforms.uLevel!.value = this.level;
    }

    if (this.particles) {
      const uniforms = this.particles.material.uniforms;
      uniforms.uTime!.value = this.time;
      uniforms.uLevel!.value = this.level;
    }
  }
}
