"use strict";
// The shell's fixed DOM anchors, extracted from the boot module at its cap.
// No state, handlers or transport live here.
export function studioMounts(byId) {
  const shell = byId("studioShell");
  return {
    main: byId("studioMain"), bridge: byId("studioBridge"),
    title: byId("studioTitle"),
    translatedText: [...shell.querySelectorAll("[data-i18n]")],
    translatedLabels: [...shell.querySelectorAll("[data-i18n-label]")],
    project: byId("studioProject"),
    connection: byId("studioConnection"),
    primary: byId("studioPrimary"),
    status: byId("studioStatus"),
    tabs: [...byId("studioNav").querySelectorAll("[data-screen]")],
    screens: {
      overview: byId("screenOverview"), workflow: byId("screenWorkflow"),
      runs: byId("screenRuns"), decisions: byId("screenDecisions"),
      agents: byId("screenAgents"),
    },
    states: {
      overview: byId("stateOverview"), workflow: byId("stateWorkflow"),
      runs: byId("stateRuns"), decisions: byId("stateDecisions"),
      agents: byId("stateAgents"),
    },
    bodyOverview: byId("bodyOverview"),
    bodyRuns: byId("bodyRuns"),
    bodyDecisions: byId("bodyDecisions"),
    bodyAgents: byId("bodyAgents"),
    toolbar: byId("workflowToolbar"),
    edges: byId("workflowEdges"),
    nodes: byId("workflowNodes"),
    inspector: byId("workflowInspector"),
    diagnostics: byId("workflowDiagnostics"),
  };
}
