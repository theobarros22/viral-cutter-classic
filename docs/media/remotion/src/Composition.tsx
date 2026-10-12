import {
  AbsoluteFill,
  CalculateMetadataFunction,
  Composition,
  interpolate,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type Props = {};

const calculateMetadata: CalculateMetadataFunction<Props> = () => {
  return {};
};

export const MyComposition = () => {
  return (
    <Composition
      id="ViralCutterLaunch"
      component={MyComponent}
      durationInFrames={660}
      fps={30}
      width={1080}
      height={1920}
      calculateMetadata={calculateMetadata}
    />
  );
};

export const MyComponent: React.FC<Props> = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame, fps, config: {damping: 18, stiffness: 120}});
  const progress = interpolate(frame, [300, 470], [0, 100], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
  const glow = interpolate(frame, [0, 660], [0.35, 0.7], {extrapolateRight: "clamp"});

  return (
    <AbsoluteFill style={{background: "#080b0d", color: "#f3f7f4", fontFamily: "Arial, sans-serif", overflow: "hidden"}}>
      <AbsoluteFill style={{background: `radial-gradient(circle at 50% 18%, rgba(188,255,38,${glow * 0.18}), transparent 38%), linear-gradient(160deg, #080b0d 0%, #11191b 100%)`}} />
      <TopBar />
      <Sequence durationInFrames={110}>
        <Hook progress={enter} />
      </Sequence>
      <Sequence from={90} durationInFrames={150}>
        <PipelineScene label="IMPORTAR VÍDEO" step="01" progress={spring({frame: Math.max(0, frame - 90), fps, config: {damping: 16}})}>
          <UploadCard />
        </PipelineScene>
      </Sequence>
      <Sequence from={220} durationInFrames={170}>
        <PipelineScene label="DETECTAR PARTICIPANTES" step="02" progress={spring({frame: Math.max(0, frame - 220), fps, config: {damping: 16}})}>
          <DetectionCard />
        </PipelineScene>
      </Sequence>
      <Sequence from={370} durationInFrames={160}>
        <PipelineScene label="ENQUADRAMENTO 9:16" step="03" progress={spring({frame: Math.max(0, frame - 370), fps, config: {damping: 16}})}>
          <FramingCard />
        </PipelineScene>
      </Sequence>
      <Sequence from={510} durationInFrames={150}>
        <PipelineScene label="EXPORTAR CORTES" step="04" progress={spring({frame: Math.max(0, frame - 510), fps, config: {damping: 16}})}>
          <ExportCard progress={progress} />
        </PipelineScene>
      </Sequence>
      <Footer frame={frame} />
    </AbsoluteFill>
  );
};

const TopBar = () => <div style={{position: "absolute", top: 76, left: 76, right: 76, display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 2}}><div style={{fontSize: 34, fontWeight: 800, color: "#caff2f"}}>Viral Cutter <span style={{color: "#f3f7f4"}}>Classic</span></div><div style={{fontSize: 22, color: "#99aaa5"}}>PROCESSAMENTO LOCAL</div></div>;

const Hook = ({progress}: {progress: number}) => <div style={{position: "absolute", inset: 0, display: "flex", flexDirection: "column", justifyContent: "center", padding: 80, transform: `translateY(${interpolate(progress, [0, 1], [50, 0])}px)`, opacity: progress}}><div style={{color: "#caff2f", fontSize: 24, letterSpacing: 5, fontWeight: 700}}>EDITOR LOCAL PARA PODCASTS</div><div style={{fontSize: 82, lineHeight: 1.03, fontWeight: 800, marginTop: 26}}>Podcast longo.<br/>Cortes verticais.<br/><span style={{color: "#caff2f"}}>Sem perder as pessoas.</span></div><div style={{marginTop: 50, width: 170, height: 8, borderRadius: 8, background: "#caff2f"}} /></div>;

const PipelineScene = ({label, step, progress, children}: {label: string; step: string; progress: number; children: React.ReactNode}) => <div style={{position: "absolute", inset: 0, padding: "260px 70px 250px", opacity: progress, transform: `translateY(${interpolate(progress, [0, 1], [45, 0])}px)`}}><div style={{display: "flex", gap: 18, alignItems: "center", color: "#caff2f", fontSize: 24, fontWeight: 800, letterSpacing: 3}}><span style={{border: "1px solid #caff2f", borderRadius: 8, padding: "7px 12px"}}>{step}</span>{label}</div><div style={{marginTop: 38}}>{children}</div></div>;

const Panel = ({children}: {children: React.ReactNode}) => <div style={{background: "rgba(26,33,35,.92)", border: "1px solid #3a4748", borderRadius: 28, padding: 30, boxShadow: "0 24px 80px rgba(0,0,0,.35)"}}>{children}</div>;

const UploadCard = () => <Panel><div style={{height: 330, border: "2px dashed #526262", borderRadius: 20, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 18}}><div style={{fontSize: 68, color: "#caff2f"}}>↑</div><div style={{fontSize: 30, fontWeight: 700}}>Solte o arquivo aqui</div><div style={{color: "#9aa7a4", fontSize: 24}}>ou clique para fazer upload</div></div><div style={{marginTop: 24, display: "flex", gap: 16}}><div style={{flex: 1, background: "#101618", borderRadius: 14, padding: 20, color: "#aab7b2"}}>Link do vídeo (YouTube etc.)</div><div style={{background: "#586064", borderRadius: 14, padding: "20px 28px", color: "#fff", fontWeight: 700}}>↓ BAIXAR</div></div></Panel>;

const DetectionCard = () => <Panel><div style={{display: "flex", gap: 18}}>{["Pessoa 1", "Pessoa 2", "Pessoa 3"].map((name, i) => <div key={name} style={{flex: 1, height: 250, borderRadius: 18, background: `linear-gradient(145deg, ${i === 1 ? "#273b3e" : "#1b2528"}, #101415)`, border: `2px solid ${i < 2 ? "#caff2f" : "#4d5b5b"}`, display: "flex", alignItems: "flex-end", padding: 18, fontSize: 22, fontWeight: 700}}>{name}</div>)}</div><div style={{marginTop: 25, background: "#102e31", color: "#62f0d0", borderRadius: 14, padding: 18, fontSize: 22}}>✓ Rostos encontrados · análise pronta</div></Panel>;

const FramingCard = () => <Panel><div style={{display: "flex", gap: 20, alignItems: "center"}}><div style={{width: 300, height: 500, borderRadius: 18, border: "3px solid #caff2f", background: "linear-gradient(160deg,#425b5d,#131b1d 70%)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 100}}>◉</div><div style={{fontSize: 44, color: "#caff2f"}}>+</div><div style={{width: 300, height: 500, borderRadius: 18, border: "3px solid #56e6d0", background: "linear-gradient(160deg,#31494c,#101719 70%)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 100}}>◉</div></div><div style={{marginTop: 25, display: "flex", justifyContent: "space-between", color: "#b6c3be", fontSize: 22}}><span>SOLO</span><span>SPLIT · DUAS PESSOAS</span></div></Panel>;

const ExportCard = ({progress}: {progress: number}) => <Panel><div style={{fontSize: 28, fontWeight: 700}}>Exportando cortes verticais</div><div style={{marginTop: 34, height: 18, background: "#263032", borderRadius: 20, overflow: "hidden"}}><div style={{height: "100%", width: `${progress}%`, background: "linear-gradient(90deg,#caff2f,#5de7ce)", borderRadius: 20}} /></div><div style={{marginTop: 16, display: "flex", justifyContent: "space-between", color: "#caff2f", fontSize: 24}}><span>{Math.round(progress)}%</span><span>1080 × 1920</span></div><div style={{marginTop: 34, padding: 20, background: "#102e31", borderRadius: 16, color: "#72f2d3", fontSize: 22}}>✓ Validação concluída · retomada habilitada</div></Panel>;

const Footer = ({frame}: {frame: number}) => <div style={{position: "absolute", bottom: 74, left: 76, right: 76, display: "flex", justifyContent: "space-between", color: frame > 560 ? "#caff2f" : "#75837f", fontSize: 22, letterSpacing: 2}}><span>github.com/theobarros22/viral-cutter-classic</span><span>CONTRIBUA · TESTE · MELHORE</span></div>;
