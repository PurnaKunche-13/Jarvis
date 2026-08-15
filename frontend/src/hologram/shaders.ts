import { SIMPLEX_3D } from './noise.glsl';

/**
 * All motion lives in the shaders: the CPU only pushes a handful of uniforms per
 * frame, so the hologram stays smooth regardless of React re-renders.
 */

export const orbVertexShader = /* glsl */ `
uniform float uTime;
uniform float uAmplitude;
uniform float uLevel;
uniform float uDetail;

varying vec3 vNormal;
varying vec3 vViewDir;
varying float vDisplacement;

${SIMPLEX_3D}

void main() {
  vec3 pos = position;
  float slow = snoise(pos * 1.15 + vec3(0.0, uTime * 0.22, 0.0));
  float fast = snoise(pos * (2.7 + uDetail) - vec3(uTime * 0.55, 0.0, uTime * 0.31));
  float displacement = (slow * 0.65 + fast * 0.35) * uAmplitude * (0.45 + uLevel * 1.55);

  pos += normal * displacement;
  vDisplacement = displacement;

  vec4 viewPosition = modelViewMatrix * vec4(pos, 1.0);
  vNormal = normalize(normalMatrix * normal);
  vViewDir = normalize(-viewPosition.xyz);
  gl_Position = projectionMatrix * viewPosition;
}
`;

export const orbFragmentShader = /* glsl */ `
uniform vec3 uCoreColor;
uniform vec3 uEdgeColor;
uniform float uOpacity;
uniform float uScan;
uniform float uTime;

varying vec3 vNormal;
varying vec3 vViewDir;
varying float vDisplacement;

void main() {
  float fresnel = pow(1.0 - clamp(dot(vNormal, vViewDir), 0.0, 1.0), 2.2);
  float ridges = smoothstep(0.0, 0.22, abs(vDisplacement));
  float scan = 0.5 + 0.5 * sin((vNormal.y * 34.0) - uTime * 2.4);

  vec3 color = mix(uCoreColor, uEdgeColor, fresnel);
  color += uEdgeColor * ridges * 0.35;
  color += uEdgeColor * scan * uScan;

  float alpha = uOpacity * (0.18 + fresnel * 0.95 + ridges * 0.2);
  gl_FragColor = vec4(color, clamp(alpha, 0.0, 1.0));
}
`;

export const ringVertexShader = /* glsl */ `
uniform float uTime;
uniform float uLevel;
uniform float uWobble;

varying vec2 vUv;

${SIMPLEX_3D}

void main() {
  vUv = uv;
  vec3 pos = position;
  float wave = snoise(vec3(pos.xy * 1.6, uTime * 0.35));
  pos.z += wave * uWobble * (0.3 + uLevel);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
`;

export const ringFragmentShader = /* glsl */ `
uniform vec3 uColor;
uniform float uTime;
uniform float uOpacity;
uniform float uSpin;
uniform float uTicks;

varying vec2 vUv;

void main() {
  float angle = vUv.x * 6.28318530718;
  float sweep = fract(vUv.x - uTime * uSpin);
  float head = smoothstep(0.0, 0.08, sweep) * smoothstep(0.34, 0.0, sweep);
  float ticks = step(0.72, fract(angle * uTicks));
  float band = smoothstep(0.0, 0.45, vUv.y) * smoothstep(1.0, 0.55, vUv.y);

  float intensity = band * (0.14 + head * 0.9 + ticks * 0.22);
  gl_FragColor = vec4(uColor, intensity * uOpacity);
}
`;

export const particleVertexShader = /* glsl */ `
uniform float uTime;
uniform float uLevel;
uniform float uSize;
uniform float uPixelRatio;

attribute float aSeed;
attribute float aRadius;

varying float vFade;

void main() {
  float spin = uTime * (0.06 + aSeed * 0.12);
  float radius = aRadius * (1.0 + uLevel * 0.12);
  vec3 pos = position;
  float c = cos(spin);
  float s = sin(spin);
  pos.xz = mat2(c, -s, s, c) * normalize(pos.xz + 1e-5) * radius;
  pos.y += sin(uTime * (0.4 + aSeed) + aSeed * 6.28) * 0.12;

  vec4 viewPosition = modelViewMatrix * vec4(pos, 1.0);
  gl_Position = projectionMatrix * viewPosition;
  gl_PointSize = uSize * uPixelRatio * (1.0 + uLevel) * (300.0 / -viewPosition.z);
  vFade = 0.35 + 0.65 * aSeed;
}
`;

export const particleFragmentShader = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacity;

varying float vFade;

void main() {
  float d = length(gl_PointCoord - vec2(0.5));
  if (d > 0.5) discard;
  float falloff = smoothstep(0.5, 0.0, d);
  gl_FragColor = vec4(uColor, falloff * vFade * uOpacity);
}
`;
