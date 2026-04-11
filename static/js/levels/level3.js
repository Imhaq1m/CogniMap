/**
 * Level 3: Apply — Connect concepts, AI adversarially challenges.
 */

const Level3 = {
  async addEdge(fromNode, toNode, justification) {
    return API.post("/api/level3/add-edge", {
      from_node: fromNode,
      to_node: toNode,
      justification,
      participant_id: "P01",
    });
  },
};
