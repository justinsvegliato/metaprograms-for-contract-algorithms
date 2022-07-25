import copy
import math
import random
from itertools import permutations

import numpy as np

from src.classes.nodes.node import Node
from src.classes.performance_profile import PerformanceProfile
from src.classes.time_allocation import TimeAllocation


class ContractProgram:
    """
    Structures a directed-acyclic graph (DAG) as a contract program by applying a budget on a DAG of
    contract algorithms. The edges are directed from the leaves to the root.

    :param: budget : non-negative int, required
        The budget of the contract program represented as seconds
    :param: dag : DAG, required
        The DAG that the contract program inherits
    :param: scale : float, required
        The scale that transforms the printed expected utility for easier interpretation
    :param: decimals : int, required
        The number of decimal points that adjusts the printed expected utility and allocations for easier interpretation
    :param: quality_interval : float, required
        The interval used to help calculate the performance profiles (probabilities)
    :param: time_interval : float, required
        The interval used to help calculate the performance profiles (probabilities)
    """
    POPULOUS_FILE_NAME = "populous.json"

    def __init__(self, dag, budget, scale, decimals, quality_interval, time_interval, time_step_size):
        self.performance_profile = PerformanceProfile(program_dag=dag, file_name=self.POPULOUS_FILE_NAME,
                                                      time_interval=time_interval, time_limit=budget,
                                                      quality_interval=quality_interval, time_step_size=time_step_size)
        self.dag = dag
        self.budget = budget
        self.scale = scale
        self.decimals = decimals
        self.allocations = None

    @staticmethod
    def global_utility(qualities) -> float:
        """
        Gives a utility given the qualities of the parents of the current node

        :param qualities: Qualities[], required
                The qualities that were outputted for each contract algorithm in the DAG
        :return: float
        """
        return math.prod(qualities)

    def global_expected_utility(self, time_allocations) -> float:
        """
        Gives the expected utility of the contract program given the performance profiles of the nodes
        (i.e., the probability distribution of each contract program's conditional performance profile) and the
        global utility

        Assumption: A time-allocation is given to each node in the contract program

        :param time_allocations: float[], required
                The time allocations for each contract algorithm
        :return: float
        """
        probability = 1.0
        average_qualities = []

        # The for-loop is a breadth-first search given that the time-allocations is ordered correctly
        for (id, time) in enumerate(time_allocations):
            node = self.find_node(id)

            if node.traversed:
                pass

            else:
                node.traversed = True

                if node.expression_type != "conditional":
                    parent_qualities = self.performance_profile.find_parent_qualities(node, time_allocations, depth=0)

                    # Outputs a list of qualities from the instances at the specified time given a quality mapping
                    qualities = self.performance_profile.query_quality_list_on_interval(time.time, id, parent_qualities=parent_qualities)

                    # Calculates the average quality on the list of qualities for querying
                    average_quality = self.performance_profile.average_quality(qualities)

                    average_qualities.append(average_quality)

                    probability *= self.performance_profile.query_probability_contract_expression(average_quality, qualities)

                # Catches node.expression_type == "conditional"
                else:
                    # TODO: Allow this to accept arbitrary subtrees and calculate the probability
                    # Here, we assume that the parents are the same for both conditional branches
                    parent_qualities_true = self.performance_profile.find_parent_qualities(node.children[0], time_allocations, depth=0)
                    node.children[0].traversed = True
                    parent_qualities_false = self.performance_profile.find_parent_qualities(node.children[1], time_allocations, depth=0)
                    node.children[1].traversed = True

                    # Outputs a list of qualities from the instances at the specified time given a quality mapping
                    qualities_true = self.performance_profile.query_quality_list_on_interval(time.time, node.children[0].id,
                                                                                             parent_qualities=parent_qualities_true)
                    qualities_false = self.performance_profile.query_quality_list_on_interval(time.time, node.children[1].id,
                                                                                              parent_qualities=parent_qualities_false)

                    qualities_branches = [qualities_true, qualities_false]

                    # Calculates the average quality on the list of qualities for querying
                    average_quality_true = self.performance_profile.average_quality(qualities_true)
                    average_quality_false = self.performance_profile.average_quality(qualities_false)

                    average_quality_list = [average_quality_true, average_quality_false]

                    # We let the average quality of the conditional to be the average quality of its branches
                    average_qualities.append(self.performance_profile.average_quality(average_quality_list))

                    probability *= self.performance_profile.query_probability_conditional_expression(node, average_quality_list, qualities_branches)

        expected_utility = probability * self.global_utility(average_qualities)

        # Reset the traversed pointers on the nodes
        self.reset_traversed()

        return expected_utility

    def naive_hill_climbing(self, decay=1.1, threshold=.0001, verbose=False) -> [float]:
        """
        Does naive hill climbing search by randomly replacing a set amount of time s between two different contract
        algorithms. If the expected value of the root node of the contract algorithm increases, we commit to the
        replacement; else, we divide s by a decay rate and repeat the above until s reaches some threshold by which we
        terminate.

        :param verbose: Verbose mode
        :param threshold: float, the threshold of the temperature decay during annealing
        :param decay: float, the decay rate of the temperature during annealing
        :return: A stream of optimized time allocations associated with each contract algorithm
        """
        time_switched = self.find_uniform_allocation(self.budget)

        while time_switched > threshold:
            possible_local_max = []
            # Go through all permutations of the time allocations
            for permutation in permutations(self.allocations, 2):

                # Makes a deep copy to avoid pointers to the same list
                adjusted_allocations = copy.deepcopy(self.allocations)

                # Avoids all permutations that include the conditional node
                if self.find_node(permutation[0].node_id).expression_type == "conditional" or self.find_node(
                        permutation[1].node_id).expression_type == "conditional":
                    continue

                # Avoids exchanging time between two branch nodes of a conditional
                # TODO: Needs to be changed to avoid exchanging time between two arbitrary subtrees instead of the immediate children
                elif self.child_of_conditional(self.find_node(permutation[0].node_id)) and self.child_of_conditional(
                        self.find_node(permutation[1].node_id)):
                    continue

                # Avoids exchanging time with itself
                elif permutation[0].node_id == permutation[1].node_id:
                    continue

                # Avoids negative time allocation
                elif adjusted_allocations[permutation[0].node_id].time - time_switched < 0:
                    continue

                else:
                    # Check if node is child of conditional so that both children of the conditional are allocated same time
                    if self.child_of_conditional(self.find_node(permutation[0].node_id)):
                        # find the neighbor node
                        neighbor = self.find_neighbor_branch(self.find_node(permutation[0].node_id))

                        # Adjust the allocation to the traversed node under the conditional
                        adjusted_allocations[permutation[0].node_id].time -= time_switched
                        # Adjust allocation to the neighbor in parallel
                        adjusted_allocations[neighbor.id].time -= time_switched

                        # Adjust allocation to then non-child of a conditional
                        adjusted_allocations[permutation[1].node_id].time += time_switched

                    # Check if node is child of conditional so that both children of the conditional are allocated same time
                    elif self.child_of_conditional(self.find_node(permutation[1].node_id)):
                        # find the neighbor node
                        neighbor = self.find_neighbor_branch(self.find_node(permutation[1].node_id))

                        # Adjust the allocation to the traversed node under the conditional
                        adjusted_allocations[permutation[1].node_id].time += time_switched
                        # Adjust allocation to the neighbor in parallel
                        adjusted_allocations[neighbor.id].time += time_switched

                        # Adjust allocation to then non-child of a conditional
                        adjusted_allocations[permutation[0].node_id].time -= time_switched

                    else:
                        adjusted_allocations[permutation[0].node_id].time -= time_switched
                        adjusted_allocations[permutation[1].node_id].time += time_switched

                    if self.global_expected_utility(adjusted_allocations) > self.global_expected_utility(self.allocations):
                        possible_local_max.append(adjusted_allocations)

                    eu_adjusted = self.global_expected_utility(adjusted_allocations) * self.scale
                    eu_original = self.global_expected_utility(self.allocations) * self.scale
                    print_allocations = [i.time for i in adjusted_allocations]
                    temp_time_switched = time_switched

                    # Check for rounding
                    if self.decimals is not None:
                        print_allocations = [round(i.time, self.decimals) for i in adjusted_allocations]
                        eu_adjusted = round(eu_adjusted, self.decimals)
                        eu_original = round(eu_original, self.decimals)
                        self.global_expected_utility(self.allocations) * self.scale
                        temp_time_switched = round(temp_time_switched, self.decimals)

                    if verbose:
                        message = "Amount of time switched: {:<12} ==> EU(adjusted): {:<12} EU(original): {:<12} ==> Allocations: {}"
                        print(message.format(temp_time_switched, eu_adjusted, eu_original, print_allocations))

            # arg max here
            if possible_local_max:
                best_allocation = max([self.global_expected_utility(j) for j in possible_local_max])
                for j in possible_local_max:
                    if self.global_expected_utility(j) == best_allocation:
                        # Make a deep copy to avoid pointers to the same list
                        self.allocations = copy.deepcopy(j)
            # if local max wasn't found
            else:
                time_switched = time_switched / decay

        return self.allocations

    def uniform_budget(self) -> [TimeAllocation]:
        # TODO: take into account embedded conditionals later
        """
        Partitions the budget into equal partitions relative to the order of the DAG

        :return: TimeAllocation[]
        """
        time_allocations = []
        budget = float(self.budget)

        # Do an initial pass to find the conditionals to adjust the budget
        for node_id in range(0, self.dag.order):
            if self.find_node(node_id).expression_type == "conditional":
                # Assume every conditional takes tau time
                tau = self.performance_profile.calculate_tau()
                # Subtract tau from the budget
                budget -= tau
                # Add the time allocation at a specified index
                time_allocations.insert(node_id, TimeAllocation(node_id, tau))

        # Do a second pass to add in the rest of the allocations wrt a uniform allocation
        for node_id in range(0, self.dag.order):
            # Continue since we already did the initial pass
            if self.find_node(node_id).expression_type == "conditional":
                continue

            allocation = self.find_uniform_allocation(budget)
            time_allocations.insert(node_id, TimeAllocation(node_id, allocation))

        return time_allocations

    def dirichlet_budget(self) -> [TimeAllocation]:
        """
        Partitions the budget into random partitions such that they add to the budget using a Dirichlet distribution

        :return: TimeAllocation
        """
        number_of_conditionals = self.count_conditionals()

        # Remove the one of the branches and the conditional node before applying the Dirichlet distribution
        allocations_array = np.random.dirichlet(np.ones(self.dag.order - (2 * number_of_conditionals)), size=1).squeeze()

        allocations_list = allocations_array.tolist()

        # Multiply all elements by the budget and remove tau times if conditionals exist
        # TODO: Later make this a list, if multiple conditionals exist
        tau = self.performance_profile.calculate_tau()

        # Transform the list wrt the budget
        allocations_list = [time * (self.budget - (number_of_conditionals * tau)) for time in allocations_list]

        # Insert the conditional nodes into the list with tau time and
        # Search for conditional branches and append a neighbor since we removed it prior to using Dirichlet
        index = 0
        while index < len(allocations_list):
            # We insert a conditional branch and the conditional node since they were omitted before
            if self.child_of_conditional(self.find_node(index)):
                # Insert the neighbor branch with same time allocation
                allocations_list.insert(index, allocations_list[index])

                index += 1

                # Insert the conditional node with tau time allocation
                allocations_list.insert(index + 1, tau)
            index += 1

        return [TimeAllocation(node_id=id, time=time) for (id, time) in enumerate(allocations_list)]

    def uniform_budget_with_noise(self, perturbation_bound=.1, iterations=10) -> [TimeAllocation]:
        """
        Partitions the budget into a uniform distribution with added noise

        :return: TimeAllocation[]
        """
        time_allocations = self.uniform_budget()
        i = 0

        while i <= iterations:
            # Initialize a random number to be used as a perturbation
            random_number = random.uniform(0, perturbation_bound)

            # Get two random indexes from the list of time allocations
            random_index_0 = random.randint(0, self.dag.order - 1)
            random_index_1 = random.randint(0, self.dag.order - 1)

            # Do some checks to ensure the properties of conditional expressions are held
            # Avoid all exchanges that include the conditional node
            if self.find_node(random_index_0).expression_type == "conditional" or self.find_node(
                    random_index_1).expression_type == "conditional":
                continue

            # Avoids exchanging time between two branch nodes of a conditional
            elif self.child_of_conditional(self.find_node(random_index_0)) and self.child_of_conditional(
                    self.find_node(random_index_1)):
                continue

            # Avoids exchanging time with itself
            elif random_index_0 == random_index_1:
                continue

            elif time_allocations[random_index_0].time - random_number < 0:
                continue

            else:
                i += 1

                # Check if is child of conditional so that both children of the conditional are allocated same time
                if self.child_of_conditional(self.find_node(random_index_0)):
                    # find the neighbor node
                    neighbor = self.find_neighbor_branch(self.find_node(random_index_0))

                    # Adjust the allocation to the traversed node under the conditional
                    time_allocations[random_index_0].time -= random_number
                    # Adjust allocation to the neighbor in parallel
                    time_allocations[neighbor.id].time -= random_number

                    # Adjust allocation to then non-child of a conditional
                    time_allocations[random_index_1].time += random_number

                elif self.child_of_conditional(self.find_node(random_index_1)):
                    # find the neighbor node
                    neighbor = self.find_neighbor_branch(self.find_node(random_index_1))

                    # Adjust the allocation to the traversed node under the conditional
                    time_allocations[random_index_1].time += random_number
                    # Adjust allocation to the neighbor in parallel
                    time_allocations[neighbor.id].time += random_number

                    # Adjust allocation to then non-child of a conditional
                    time_allocations[random_index_0].time -= random_number

                else:
                    time_allocations[random_index_0].time -= random_number
                    time_allocations[random_index_1].time += random_number

        return time_allocations

    def reset_traversed(self) -> None:
        """
        Resets the traversed pointers to Node objects

        :return: None
        """
        for node in self.dag.nodes:
            node.traversed = False

    def find_uniform_allocation(self, budget) -> float:
        """
        Finds the allocation that can uniformly be distributed given the budget

        :param budget: float
        :return: uniformed allocation
        """
        number_of_conditionals = self.count_conditionals()
        # multiply by two since the branches get an equivalent time allocation
        allocation = budget / (self.dag.order - (2 * number_of_conditionals))
        return allocation

    @staticmethod
    def find_neighbor_branch(node) -> Node:
        """
        Finds the neighbor branch of the child node of a conditional node
        Assumption: the input node is the child of a conditional node

        :param node: Node object
        :return: Node object
        """
        conditional_node = node.parents[0]
        for child in conditional_node.children:
            if child != node:
                return child

    def count_conditionals(self) -> int:
        """
        Counts the number of conditionals in the contract program

        :return: number of conditionals:
        """
        number_of_conditionals = 0
        for node_id in range(0, self.dag.order):
            if self.find_node(node_id).expression_type == "conditional":
                number_of_conditionals += 1
        return number_of_conditionals

    def find_node(self, node_id) -> Node:
        """
        Finds the node in the node list given the id

        :param: node_id: The id of the node
        :return Node object
        """
        for node in self.dag.nodes:
            if node.id == node_id:
                return node
        raise IndexError("Node not found with given id")

    @staticmethod
    def child_of_conditional(node) -> bool:
        """
        Checks whether the node is a child of a conditional

        :param: node: Node object
        :return bool
        """
        for parent in node.parents:
            if parent.expression_type == "conditional":
                return True
        return False

    @staticmethod
    def parent_of_conditional(node) -> bool:
        """
        Checks whether the node is a parent of a conditional

        :param: node: Node object
        :return bool
        """
        for child in node.children:
            if child.expression_type == "conditional":
                return True
        return False
