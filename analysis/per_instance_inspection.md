# Case Study
without (default) -> with intervention (refiner):

Pay particular attention to the trajectory steps after the intervention. Some directions to explore include:
## U → R cases: 
Why was the intervention helpful?  
What behavior changed after the guidance was provided?

## R → U cases: 
What caused the degradation?
1. The intervention itself misleading, low quality, or focused on secondary issues (e.g., difficult test setup or environment configuration) rather than the core problem (can be found in <pr_description></pr_description>)?
2. Execution non-determinism? In the new run, the agent may have taken a different path and failed for reasons that never occurred in the vanilla trajectory.
3. The executor agent fail to follow or effectively act on the guidance provided by the refiner?
4. Did the vanilla agent succeed by chance? For example, due to potential data contamination or memorization of the solution. One possible indicator: submitting a patch with no testing.
and more...