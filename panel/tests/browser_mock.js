/* Inject only into browser QA. Not loaded by the real panel. No credentials. */
window.KCF_QA = { hostCalls: [], apiCalls: [] };
window.__adobe_cep__ = {
    getSystemPath: function () { return "C:/QA/CapForge"; },
    evalScript: function (code, callback) {
        if (code.indexOf("$.evalFile") === 0) { callback(JSON.stringify({ok:true,data:true})); return; }
        var request = JSON.parse(JSON.parse(code.slice("KCF_dispatch(".length, -1)));
        window.KCF_QA.hostCalls.push(request);
        var data = null;
        if (request.action === "context") { data = {comp:{name:"QA composition",width:1920,height:1080,duration:10,frameRate:30},fonts:[{name:"ArialMT",family:"Arial",style:"Regular"},{name:"Arial-BoldMT",family:"Arial",style:"Bold"},{name:"NotoSansGeorgian-Regular",family:"Noto Sans Georgian",style:"Regular"}],presets:[]}; }
        if (request.action === "token") { data = "qa-token-only"; }
        if (request.action === "chooseMedia" || request.action === "selectedMedia") { data = {path:"/qa/clip.mp4",name:"clip.mp4"}; }
        if (request.action === "generate") { data = {name:"KCF_Captions_QA"}; }
        callback(JSON.stringify({ok:true,data:data}));
    }
};
window.fetch = function (url, options) {
    var path = url.replace("http://127.0.0.1:8765", "");
    var payload = options.body ? JSON.parse(options.body) : null;
    window.KCF_QA.apiCalls.push({path:path,payload:payload});
    var data = {};
    if (path === "/health") { data = {ok:true,version:"0.3.2",ffmpeg:true}; }
    if (path === "/providers") { data = {providers:[{id:"elevenlabs",label:"ElevenLabs Scribe v2",type:"cloud",available:true}]}; }
    if (path === "/transcribe") { data = {document:window.KCF_Transcript.demo("ka-GE"),timingQuality:"word",warnings:[]}; data.document.provider = "qa"; }
    if (path === "/regroup") { data = {document:payload.document}; }
    if (path === "/extract_audio") { data = {audio:"/qa/exports/audio.wav",duration:8}; }
    if (path === "/updates/check") { data = {available:true,version:"0.3.3",tag:"qa-build",notes:"A sample update for visual testing.",message:"An update is ready to install."}; }
    if (path === "/updates/install") { data = {started:true,message:"Setup is opening. Save your project and close After Effects before installing."}; }
    return Promise.resolve({ok:true,json:function () { return Promise.resolve(data); }});
};
