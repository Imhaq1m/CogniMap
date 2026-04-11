/**
 * Level 1: Remember — Define concepts, AI validates.
 * Stub: will contain definition input, validation, and progress tracking.
 */

const Level1 = {
  /**
   * Submit a concept definition for AI validation.
   * @param {string} concept - Concept name
   * @param {string} definition - Student's definition
   * @returns {Promise<{result: string, feedback: string}>}
   */
  async validateDefinition(concept, definition) {
    return API.post("/api/level1/validate-definition", {
      concept,
      definition,
      participant_id: "P01",
    });
  },
};
