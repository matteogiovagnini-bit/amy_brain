// Neuroni decorativi attorno al nucleo di Amy.
// Canvas locale, nessuna risorsa esterna. Rispetta «Movimento: ridotto» e
// prefers-reduced-motion disegnando un solo fotogramma statico.
(function () {
  "use strict";

  const TAU = Math.PI * 2;
  const COLORS = [
    [63, 227, 255],
    [122, 242, 226],
    [47, 123, 255],
  ];
  const ACTIVE_STATES = new Set([
    "conversation",
    "processing",
    "executing",
    "speaking",
    "waiting_confirmation",
    "interrupted",
    "error",
  ]);
  const FRAME_INTERVAL = 1 / 24;
  const STATES = {
    idle: { speed: 0.7, glow: 0.75 },
    listening: { speed: 1.25, glow: 1.15 },
    conversation: { speed: 1.0, glow: 0.95 },
    processing: { speed: 1.5, glow: 1.2 },
    executing: { speed: 1.45, glow: 1.2 },
    speaking: { speed: 1.15, glow: 1.05 },
    waiting_confirmation: { speed: 0.95, glow: 1.0 },
    interrupted: { speed: 0.8, glow: 0.85 },
    error: { speed: 0.65, glow: 0.8 },
    offline: { speed: 0.45, glow: 0.5 },
  };

  let canvas = null;
  let ctx = null;
  let width = 0;
  let height = 0;
  let dpr = 1;
  let nodes = [];
  let raf = 0;
  let running = false;
  let last = 0;
  let time = 0;
  let state = "idle";
  let reduced = false;
  let active = false;
  let focused = true;
  let accumulator = 0;
  let resizeObserver = null;

  function random(min, max) {
    return min + Math.random() * (max - min);
  }

  function motionReduced() {
    const flag = document.documentElement.getAttribute("data-motion");
    const media = window.matchMedia
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false;
    return flag === "off" || (flag !== "full" && media);
  }

  function seed() {
    const min = Math.max(1, Math.min(width, height));
    const count = Math.max(28, Math.min(56, Math.round(min / 8)));
    const cx = width / 2;
    const cy = height / 2;
    nodes = [];
    for (let i = 0; i < count; i += 1) {
      const angle = random(0, TAU);
      const radius = random(0.3, 0.49) * min;
      nodes.push({
        angle: angle,
        radius: radius,
        baseRadius: radius,
        drift: random(0.02, 0.075) * (Math.random() < 0.5 ? -1 : 1),
        wobble: random(0.5, 1.4),
        phase: random(0, TAU),
        size: random(1.0, 2.4),
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
      });
    }
  }

  function resize() {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    seed();
    if (reduced || !active) draw(0);
  }

  function position(node) {
    const cx = width / 2;
    const cy = height / 2;
    const min = Math.min(width, height);
    const radius = node.baseRadius
      + Math.sin(time * node.wobble + node.phase) * min * 0.018;
    return {
      x: cx + Math.cos(node.angle) * radius,
      y: cy + Math.sin(node.angle) * radius,
    };
  }

  function draw(delta) {
    if (!ctx) return;
    const min = Math.min(width, height);
    const cfg = STATES[state] || STATES.idle;
    ctx.clearRect(0, 0, width, height);
    ctx.globalCompositeOperation = "lighter";

    const points = nodes.map(position);
    const linkDistance = min * 0.26;

    // Sinapsi: linee tenui solo tra neuroni vicini.
    for (let i = 0; i < points.length; i += 1) {
      for (let j = i + 1; j < points.length; j += 1) {
        const dx = points[i].x - points[j].x;
        const dy = points[i].y - points[j].y;
        const distance = Math.hypot(dx, dy);
        if (distance > linkDistance) continue;
        const alpha = (1 - distance / linkDistance) * 0.32 * cfg.glow;
        ctx.strokeStyle = "rgba(63, 227, 255, " + alpha.toFixed(3) + ")";
        ctx.lineWidth = 0.7;
        ctx.beginPath();
        ctx.moveTo(points[i].x, points[i].y);
        ctx.lineTo(points[j].x, points[j].y);
        ctx.stroke();
      }
    }

    // Neuroni: alone, dendriti brevi e nucleo luminoso.
    for (let i = 0; i < nodes.length; i += 1) {
      const node = nodes[i];
      const point = points[i];
      const pulse = 0.72 + 0.28 * Math.sin(time * 1.25 + node.phase);
      const color = node.color;
      const radius = node.size * (1 + 0.16 * Math.sin(time * 0.9 + node.phase));

      ctx.fillStyle = "rgba(" + color[0] + ", " + color[1] + ", " + color[2]
        + ", " + (0.07 * pulse * cfg.glow).toFixed(3) + ")";
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius * 5, 0, TAU);
      ctx.fill();

      ctx.strokeStyle = "rgba(" + color[0] + ", " + color[1] + ", " + color[2]
        + ", " + (0.32 * pulse * cfg.glow).toFixed(3) + ")";
      ctx.lineWidth = 0.65;
      for (let branch = 0; branch < 3; branch += 1) {
        const angle = node.phase + branch * 2.1 + time * 0.18;
        const length = radius * (3.1 + branch * 0.9);
        ctx.beginPath();
        ctx.moveTo(point.x, point.y);
        ctx.lineTo(
          point.x + Math.cos(angle) * length,
          point.y + Math.sin(angle) * length
        );
        ctx.stroke();
      }

      ctx.fillStyle = "rgba(" + color[0] + ", " + color[1] + ", " + color[2]
        + ", " + (0.9 * pulse * cfg.glow).toFixed(3) + ")";
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius, 0, TAU);
      ctx.fill();

      ctx.fillStyle = "rgba(235, 254, 255, " + (0.7 * pulse).toFixed(3) + ")";
      ctx.beginPath();
      ctx.arc(point.x, point.y, Math.max(0.4, radius * 0.36), 0, TAU);
      ctx.fill();
    }

    // Piccoli impulsi che scorrono lungo le orbite.
    const cfgSpeed = cfg.speed;
    for (let i = 0; i < 4; i += 1) {
      const angle = time * (0.22 + i * 0.07) * cfgSpeed + i * 2.1;
      const radius = min * (0.42 + i * 0.02);
      const x = width / 2 + Math.cos(angle) * radius;
      const y = height / 2 + Math.sin(angle) * radius;
      ctx.fillStyle = "rgba(180, 248, 255, " + (0.5 * cfg.glow).toFixed(3) + ")";
      ctx.beginPath();
      ctx.arc(x, y, 1.6, 0, TAU);
      ctx.fill();
    }

    ctx.globalCompositeOperation = "source-over";
  }

  function frame(timestamp) {
    if (!running) return;
    if (reduced || !active || document.hidden || !focused) {
      stop();
      draw(0);
      return;
    }
    if (!last) last = timestamp;
    const delta = Math.min(0.1, (timestamp - last) / 1000);
    last = timestamp;
    accumulator += delta;
    if (accumulator < FRAME_INTERVAL) {
      raf = window.requestAnimationFrame(frame);
      return;
    }
    const step = Math.min(accumulator, 0.1);
    accumulator = 0;
    time += step * ((STATES[state] || STATES.idle).speed);
    for (const node of nodes) {
      node.angle += node.drift * step;
      if (node.angle > TAU) node.angle -= TAU;
      if (node.angle < 0) node.angle += TAU;
    }
    draw(step);
    raf = window.requestAnimationFrame(frame);
  }

  function start() {
    canvas = document.getElementById("neuronField");
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    if (!ctx) return;
    reduced = motionReduced();
    resize();
    if (resizeObserver) resizeObserver.disconnect();
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(canvas);
    } else {
      window.addEventListener("resize", resize);
    }
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);
    const observer = new MutationObserver(() => {
      const next = motionReduced();
      if (next === reduced) return;
      reduced = next;
      if (reduced) {
        stop();
        draw(0);
      } else {
        startLoop();
      }
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-motion"],
    });
    updateActive();
  }

  function startLoop() {
    if (running) return;
    if (!active || reduced) {
      draw(0);
      return;
    }
    running = true;
    last = 0;
    accumulator = 0;
    raf = window.requestAnimationFrame(frame);
  }

  function stop() {
    running = false;
    if (raf) window.cancelAnimationFrame(raf);
    raf = 0;
  }

  function updateActive() {
    active = ACTIVE_STATES.has(state) && !document.hidden && focused;
    if (active && !reduced) {
      startLoop();
    } else {
      stop();
      draw(0);
    }
  }

  function onVisibility() {
    updateActive();
  }

  function onFocus() {
    focused = true;
    updateActive();
  }

  function onBlur() {
    focused = false;
    updateActive();
  }

  function setState(next) {
    const value = STATES[next] ? next : "idle";
    if (value === state) return;
    state = value;
    updateActive();
  }

  window.AmyNeurons = { start: start, setState: setState };
})();
