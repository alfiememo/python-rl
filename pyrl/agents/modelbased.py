
# Author: Will Dabney

from rlglue.agent.Agent import Agent
from rlglue.agent import AgentLoader as AgentLoader
from rlglue.types import Action
from rlglue.types import Observation
from rlglue.utils import TaskSpecVRLGLUE3

from random import Random
import numpy
import sys
import copy

from pyrl.agents.models import batch_model
from pyrl.agents.planners import fitted_qiteration

class ModelBasedAgent(Agent):
	"""
	ModelBasedAgent provides a reinforcement learning agent which plans, using the planner class provided, 
	over a model of the domain, learned by the model learning class provided. So, essentially this class is 
	just a wrapper around the real functionality of the planner and modeling classes.
        """

	def __init__(self, gamma, model, planner, model_params={}, planner_params={}):
		"""Inits ModelBasedAgent with discount factor, model/planner classes, and parameters for these classes.
		
		Args:
			gamma: The discount factor for the domain
			model: The model learner class
			planner: The planner class which will interface with the model
			model_params: Parameters for the model class
			planner_params: Parameters for the planner class
		"""
		self.randGenerator = Random()	
		self.lastAction=Action()
		self.lastObservation=Observation()

		self.gamma = gamma
		self.model_class = model
		self.planner_class = planner
		self.model = None
		self.planner = None
		self.model_params = model_params
		self.planner_params = planner_params
		self.epsilon = 0.0

	def agent_init(self,taskSpec):
		"""Initialize the RL agent.

		Args:
			taskSpec: The RLGlue task specification string.
		"""
		# Parse the task specification and set up the weights and such
		TaskSpec = TaskSpecVRLGLUE3.TaskSpecParser(taskSpec)
		if TaskSpec.valid:
			# Check observation form, and then set up number of features/states
			assert len(TaskSpec.getDoubleObservations()) + len(TaskSpec.getIntObservations()) >0, \
			    "expecting at least one continuous or discrete observation"
			self.numStates=len(TaskSpec.getDoubleObservations())
			self.discStates = numpy.array(TaskSpec.getIntObservations())
			self.numDiscStates = int(reduce(lambda a, b: a * (b[1] - b[0] + 1), self.discStates, 1.0)) 

			# Check action form, and then set number of actions
			assert len(TaskSpec.getIntActions())==1, "expecting 1-dimensional discrete actions"
			assert len(TaskSpec.getDoubleActions())==0, "expecting no continuous actions"
			assert not TaskSpec.isSpecial(TaskSpec.getIntActions()[0][0]), " expecting min action to be a number not a special value"
			assert not TaskSpec.isSpecial(TaskSpec.getIntActions()[0][1]), " expecting max action to be a number not a special value"
			self.numActions=TaskSpec.getIntActions()[0][1]+1;
			
			self.model = self.model_class(self.numDiscStates, TaskSpec.getDoubleObservations(), \
							      self.numActions, TaskSpec.getRewardRange()[0], **self.model_params)
			self.planner = self.planner_class(self.gamma, self.model, params=self.planner_params)
			
		else:
			print "Task Spec could not be parsed: "+taskSpecString;

		self.lastAction=Action()
		self.lastObservation=Observation()


	def getAction(self, state, discState):
		"""Get the action under the current plan policy for the given state.
		
		Args:
			state: The array of continuous state features
			discState: The integer representing the current discrete state value

		Returns:
			The current greedy action under the planned policy for the given state.
		"""
		if self.randGenerator.random() < self.epsilon:
			return self.randGenerator.randint(0,self.numActions-1)

		s = numpy.zeros((len(state) + 1,))
		s[0] = discState
		s[1:] = state
		a = self.planner.getAction(s)
		return a
		
	def getDiscState(self, state):
		"""Return the integer value representing the current discrete state.
		
		Args:
			state: The array of integer state features

		Returns:
			The integer value representing the current discrete state
		"""
		if self.numDiscStates > 1:
			x = numpy.zeros((self.numDiscStates,))
			mxs = self.discStates[:,1] - self.discStates[:,0] + 1
			mxs = numpy.array(list(mxs[:0:-1].cumprod()[::-1]) + [1])
			x = numpy.array(state) - self.discStates[:,0]
			return (x * mxs).sum()
		else:
			return 0

	def agent_start(self,observation):
		"""Start an episode for the RL agent.
		
		Args:
			observation: The first observation of the episode. Should be an RLGlue Observation object.

		Returns:
			The first action the RL agent chooses to take, represented as an RLGlue Action object.
		"""
		theState = numpy.array(list(observation.doubleArray))
		thisIntAction=self.getAction(theState, self.getDiscState(observation.intArray))
		returnAction=Action()
		returnAction.intArray=[thisIntAction]

		self.lastAction=copy.deepcopy(returnAction)
		self.lastObservation=copy.deepcopy(observation)
		
		return returnAction
	
	def agent_step(self,reward, observation):
		"""Take one step in an episode for the agent, as the result of taking the last action.
		
		Args:
			reward: The reward received for taking the last action from the previous state.
			observation: The next observation of the episode, which is the consequence of taking the previous action.

		Returns:
			The next action the RL agent chooses to take, represented as an RLGlue Action object.
		"""
		newState = numpy.array(list(observation.doubleArray))
		lastState = numpy.array(list(self.lastObservation.doubleArray))
		lastAction = self.lastAction.intArray[0]

		newDiscState = self.getDiscState(observation.intArray)
		lastDiscState = self.getDiscState(self.lastObservation.intArray)

		phi_t = numpy.zeros((self.numStates+1,))
		phi_tp = numpy.zeros((self.numStates+1,))
		phi_t[0] = lastDiscState
		phi_t[1:] = lastState
		phi_tp[0] = newDiscState
		phi_tp[1:] = newState

		print ','.join(map(str, lastState))

		self.planner.updateExperience(phi_t, lastAction, phi_tp, reward)

		newIntAction = self.getAction(newState, newDiscState)
		returnAction=Action()
		returnAction.intArray=[newIntAction]
		
		self.lastAction=copy.deepcopy(returnAction)
		self.lastObservation=copy.deepcopy(observation)
		return returnAction

	def agent_end(self,reward):
		"""Receive the final reward in an episode, also signaling the end of the episode.
		
		Args:
			reward: The reward received for taking the last action from the previous state.
		"""
		lastState = numpy.array(list(self.lastObservation.doubleArray))
		lastAction = self.lastAction.intArray[0]
		lastDiscState = self.getDiscState(self.lastObservation.intArray)

		phi_t = numpy.zeros((self.numStates+1,))
		phi_t[0] = lastDiscState
		phi_t[1:] = lastState

		self.planner.updateExperience(phi_t, lastAction, None, reward)

	def agent_cleanup(self):
		"""Perform any clean up operations before the end of an experiment."""
		pass
	
	def agent_message(self,inMessage):
		"""Receive a message from the environment or experiment and respond.
		
		Args:
			inMessage: A string message sent by either the environment or experiment to the agent.

		Returns:
			A string response message.
		"""
		return "ModelBasedAgent(Python) does not understand your message."

# If executed as a standalone script this will default to RLGlue network mode.
# Some parameters can be passed at the command line to customize behavior.
if __name__=="__main__":
	import argparse
	parser = argparse.ArgumentParser(description='Run ModelBasedAgent in network mode')
	parser.add_argument("--gamma", type=float, default=0.99, help="Discount factor")
	parser.add_argument("--model", type=str, default="knn", help="What model class to use", choices=["knn", "randforest", "svm", "gp"])
	parser.add_argument("--planner", type=str, default="fitqit", help="What planner class to use", choices=["fitqit"])
	parser.add_argument("--svmde",  action='store_true', help="Use the one class SVM density estimator for known/unknown distinctions.")
	args = parser.parse_args()

	model_params = {}
	planner_params = {}
	model_class = None
	planner_class = None

	if args.model == "knn":
		model_params = {"update_freq": 20, "known_threshold": 0.95, "max_experiences": 700}
		if args.svmde:
			model_class = batch_model.KNNSVM
		else:
			model_class = batch_model.KNNBatchModel
	elif args.model == "randforest":
		model_params = {"known_threshold": 0.95, "max_experiences": 800, "importance_weight": True}		
		if args.svmde:
			model_class = model_class = batch_model.RandForestSVM
		else:
			model_class = batch_model.RandomForestBatchModel
	elif args.model == "svm":
		model_params = {"known_threshold": 0.95, "max_experiences": 500, "importance_weight": True}
		if args.svmde:
			model_class = batch_model.SVM2
		else:
			model_class = batch_model.SVMBatchModel
	elif args.model == "gp":
		model_params = {"max_experiences": 300, "nugget": 1.0e-10, "random_start": 100}
		if args.svmde:
			model_class = batch_model.GPSVM
		else:
			model_class = batch_model.GaussianProcessBatchModel

	if args.planner == "fitqit":
		planner_params = {"basis": "fourier", "regressor": "ridge", "iterations": 1000, "support_size": 50, "resample": 15}
		planner_class = fitted_qiteration.FittedQIteration
	
	AgentLoader.loadAgent(ModelBasedAgent(args.gamma, model_class, planner_class, model_params, planner_params))

