import sys
from typing import List
import copy
import math
from itertools import permutations
# import numpy as np

sys.path.append("/Users/masonnakamura/Local-Git/mca/src")

from classes import utils  # noqa
from classes.nodes.node import Node  # noqa
from classes.performance_profile import PerformanceProfile  # noqa
from classes.initialize_allocations import InitializeAllocations  # noqa


class ContractProgram:
    """
    Structures a directed-acyclic graph (DAG) as a contract program by applying a budget on a DAG of
    contract algorithms. The edges are directed from the leaves to the root.

    :param: budget : non-negative int, required
        The budget of the contract program represented as seconds
    :param: program_dag : DAG, required
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

    def __init__(self, program_id, parent_program, child_programs, program_dag, budget, scale, decimals,
                 quality_interval, time_interval, time_step_size, in_subtree, generator_dag, expected_utility_type, possible_qualities,
                 number_of_loops=None):

        self.program_id = program_id
        self.subprogram_expression_type = None
        self.program_dag = program_dag
        self.budget = budget
        self.scale = scale
        self.decimals = decimals
        self.quality_interval = quality_interval
        self.time_interval = time_interval
        self.time_step_size = time_step_size
        self.allocations = None

        self.in_subtree = in_subtree
        # Pointer to the parent program that the subprogram is an induced subgraph of
        self.parent_program = parent_program
        self.child_programs = child_programs

        self.generator_dag = generator_dag

        self.original_allocations_inner = None

        self.expected_utility_type = expected_utility_type

        self.possible_qualities = possible_qualities

        self.number_of_loops = number_of_loops

        self.performance_profile = PerformanceProfile(program_dag=self.program_dag, generator_dag=self.generator_dag,
                                                      file_name=self.POPULOUS_FILE_NAME,
                                                      time_interval=self.time_interval, time_limit=budget,
                                                      quality_interval=self.quality_interval,
                                                      time_step_size=self.time_step_size,
                                                      expected_utility_type=self.expected_utility_type)

        self.initialize_allocations = InitializeAllocations(budget=self.budget, program_dag=self.program_dag,
                                                            generator_dag=self.generator_dag,
                                                            performance_profile=self.performance_profile,
                                                            in_subtree=self.in_subtree)

    @staticmethod
    def global_utility(qualities) -> float:
        """
        Gives a utility given the qualities of the parents of the current node

        :param qualities: Qualities[], required
                The qualities that were outputted for each contract algorithm in the DAG
        :return: float
        """

        # Flatten the list of qualities
        qualities = utils.flatten(qualities)

        return math.prod(qualities)

    def global_expected_utility(self, time_allocations, original_allocations_inner=None) -> float:
        """
        Uses approximate methods or exact solutions to query the expected utility of the contract program given the time allocations
        and time allocations of the inner metareasoning problems

        Assumption: A time-allocation is given to each node in the contract program

        :param original_allocations_inner:
        :param time_allocations: float[], required
                The time allocations for each contract algorithm
        :return: float
        """
        if self.expected_utility_type == "exact":
            return (self.global_expected_utility_exact(time_allocations, original_allocations_inner))

        elif self.expected_utility_type == "approximate":
            return (self.global_expected_utility_approximate(time_allocations, original_allocations_inner))

        else:
            raise ValueError("Improper expected utility type")

    def global_expected_utility_approximate(self, time_allocations, original_allocations_inner) -> float:
        """
        Gives the estimated expected utility of the contract program given the performance profiles of the nodes
        (i.e., the probability distribution of each contract program's conditional performance profile) and the
        global utility

        Assumption: A time-allocation is given to each node in the contract program

        :param original_allocations_inner:
        :param time_allocations: float[], required
                The time allocations for each contract algorithm
        :return: float
        """
        probability = 1.0
        average_qualities = []

        # The for-loop is a breadth-first search given that the time-allocations is ordered correctly
        refactored_allocations = utils.remove_nones_time_allocations(time_allocations)

        for time_allocation in refactored_allocations:

            node = utils.find_node(time_allocation.node_id, self.program_dag)

            if (node.expression_type == "conditional" or node.expression_type == "for") and node.in_subtree:
                continue

            # Calculates the EU of a conditional expression
            elif node.expression_type == "conditional" and not node.in_subtree:

                if original_allocations_inner:
                    copied_branch_allocations = [copy.deepcopy(node.true_subprogram.allocations),
                                                 copy.deepcopy(node.false_subprogram.allocations)]

                    node.true_subprogram.allocations = original_allocations_inner[0]

                    node.false_subprogram.allocations = original_allocations_inner[1]

                # Since in conditional, but not in subtree, evaluate the inner probability of the subtree
                probability_and_qualities = self.performance_profile.query_probability_and_quality_from_conditional_expression(
                    node)

                # Multiply the current probability by the performance profile of the conditional node
                probability *= probability_and_qualities[0]

                conditional_quality = probability_and_qualities[1]

                average_qualities.append(conditional_quality)

                if original_allocations_inner:
                    node.true_subprogram.allocations = copied_branch_allocations[0]
                    node.false_subprogram.allocations = copied_branch_allocations[1]

            # Calculates the EU of a for expression
            elif node.expression_type == "for" and not node.in_subtree:

                if original_allocations_inner:

                    copied_branch_allocations = [copy.deepcopy(node.for_subprogram.allocations)]

                    node.for_subprogram.allocations = original_allocations_inner[0]

                # Since in conditional, but not in subtree, evaluate the inner probability of the subtree
                probability_and_qualities = self.performance_profile.query_probability_and_quality_from_for_expression(node)

                # Multiply the current probability by the performance profile of the conditional node
                probability *= probability_and_qualities[0]

                last_for_quality = probability_and_qualities[1]

                average_qualities.append(last_for_quality)

                if original_allocations_inner:
                    node.for_subprogram.allocations = copied_branch_allocations[0]

            else:

                # Get the parents' qualities given their time allocations
                parent_qualities = self.performance_profile.find_parent_qualities(node, time_allocations, depth=0)

                # Outputs a list of qualities from the instances at the specified time given a quality mapping
                qualities = self.performance_profile.query_quality_list_on_interval(time_allocation.time,
                                                                                    time_allocation.node_id,
                                                                                    parent_qualities=parent_qualities)

                # Calculates the average quality on the list of qualities for querying
                average_quality = self.performance_profile.average_quality(qualities)

                average_qualities.append(average_quality)

                probability *= self.performance_profile.query_probability_contract_expression(average_quality,
                                                                                              qualities)

        expected_utility = probability * self.global_utility(average_qualities)

        return expected_utility

    # def global_expected_utility_exact(self, time_allocations, original_allocations_inner) -> float:
    #     """
    #     Gives the exact expected utility of the contract program given the performance profiles of the nodes
    #     (i.e., the probability distribution of each contract program's conditional performance profile) and the
    #     global utility

    #     Assumption: A time-allocation is given to each node in the contract program

    #     :param original_allocations_inner:
    #     :param time_allocations: float[], required
    #             The time allocations for each contract algorithm
    #     :return: float
    #     """
    #     # TODO: Calculate the global expected utility using the exact EU method (9/15)

    #     probability = 1.0
    #     average_qualities = []

    #     # The for-loop is a breadth-first search given that the time-allocations is ordered correctly
    #     refactored_allocations = utils.remove_nones_time_allocations(time_allocations)

    #     for time_allocation in refactored_allocations:

    #         node = utils.find_node(time_allocation.node_id, self.program_dag)

    #         # Continue since conditional and for nodes have static times
    #         if (node.expression_type == "conditional" or node.expression_type == "for") and node.in_subtree:
    #             continue

    #         # Takes care of evaluating fixed loops with an exact expected utility in the inner metareasoning problem
    #         elif node.in_for and not node.expression_type == "for" and node.first_loop and node.in_subtree:

    #             # The leaf will be the first node of the first iteration
    #             parent_qualities = self.performance_profile.find_parent_qualities(
    #                 node=node.subprogram_parent_node, time_allocations=node.current_program.parent_program.allocations, depth=0)

    #             return self.find_exact_expected_utility(time_allocations=time_allocations, possible_qualities=self.possible_qualities, expected_utility=1,
    #                                                     current_qualities=[None for i in range(self.generator_dag.order)], parent_qualities=parent_qualities,
    #                                                     depth=0, leaves=[node], sum=0)

    #         # Calculates the EU of a conditional expression
    #         elif node.expression_type == "conditional" and not node.in_subtree:

    #             if original_allocations_inner:
    #                 copied_branch_allocations = [copy.deepcopy(node.true_subprogram.allocations),
    #                                              copy.deepcopy(node.false_subprogram.allocations)]

    #                 node.true_subprogram.allocations = original_allocations_inner[0]

    #                 node.false_subprogram.allocations = original_allocations_inner[1]

    #             # Since in conditional, but not in subtree, evaluate the inner probability of the subtree
    #             probability_and_qualities = self.performance_profile.query_probability_and_quality_from_conditional_expression(
    #                 node)

    #             # Multiply the current probability by the performance profile of the conditional node
    #             probability *= probability_and_qualities[0]

    #             conditional_quality = probability_and_qualities[1]

    #             average_qualities.append(conditional_quality)

    #             if original_allocations_inner:
    #                 node.true_subprogram.allocations = copied_branch_allocations[0]
    #                 node.false_subprogram.allocations = copied_branch_allocations[1]

    #         # Calculates the EU of a for expression
    #         elif node.expression_type == "for" and not node.in_subtree:

    #             if original_allocations_inner:

    #                 copied_branch_allocations = [copy.deepcopy(node.for_subprogram.allocations)]

    #                 node.for_subprogram.allocations = original_allocations_inner[0]

    #                 # print("subprogram allocations: {}".format(utils.print_allocations(node.for_subprogram.allocations)))

    #             # Since in conditional, but not in subtree, evaluate the inner probability of the subtree
    #             probability_and_qualities = self.performance_profile.query_probability_and_quality_from_for_expression(node)

    #             # Multiply the current probability by the performance profile of the conditional node
    #             probability *= probability_and_qualities[0]

    #             last_for_quality = probability_and_qualities[1]

    #             average_qualities.append(last_for_quality)

    #             if original_allocations_inner:
    #                 node.for_subprogram.allocations = copied_branch_allocations[0]

    #         else:

    #             # Get the parents' qualities given their time allocations
    #             parent_qualities = self.performance_profile.find_parent_qualities(node, time_allocations, depth=0)

    #             # Outputs a list of qualities from the instances at the specified time given a quality mapping
    #             qualities = self.performance_profile.query_quality_list_on_interval(time_allocation.time,
    #                                                                                 time_allocation.node_id,
    #                                                                                 parent_qualities=parent_qualities)

    #             # Calculates the average quality on the list of qualities for querying
    #             average_quality = self.performance_profile.average_quality(qualities)

    #             average_qualities.append(average_quality)

    #             probability *= self.performance_profile.query_probability_contract_expression(average_quality,
    #                                                                                           qualities)

    #     expected_utility = probability * self.global_utility(average_qualities)

    #     return expected_utility

    def global_expected_utility_exact(self, time_allocations, original_allocations_inner) -> float:
        """
        Gives the exact expected utility of the contract program given the performance profiles of the nodes
        (i.e., the probability distribution of each contract program's conditional performance profile) and the
        global utility

        Assumption: A time-allocation is given to each node in the contract program

        :param original_allocations_inner:
        :param time_allocations: float[], required
                The time allocations for each contract algorithm
        :return: float
        """
        # TODO: Calculate the global expected utility using the exact EU method (9/15)

        probability = 1.0
        average_qualities = []

        # The for-loop is a breadth-first search given that the time-allocations are ordered correctly
        refactored_allocations = utils.remove_nones_time_allocations(time_allocations)

        # TODO: Find a way to get all the leaves to find the exact (9/15)!!
        leaves = utils.find_terminal_leaves_in_dag(self.program_dag)

        return self.find_exact_expected_utility(time_allocations=time_allocations, possible_qualities=self.possible_qualities, expected_utility=1,
                                                current_qualities=[None for i in range(self.generator_dag.order)], parent_qualities=[],
                                                depth=0, leaves=leaves, sum=0)

        for time_allocation in refactored_allocations:

            node = utils.find_node(time_allocation.node_id, self.program_dag)

            # Continue since conditional and for nodes have static times
            if (node.expression_type == "conditional" or node.expression_type == "for") and node.in_subtree:
                continue

            # Takes care of evaluating fixed loops with an exact expected utility in the inner metareasoning problem
            elif node.in_for and not node.expression_type == "for" and node.first_loop and node.in_subtree:

                # The leaf will be the first node of the first iteration
                parent_qualities = self.performance_profile.find_parent_qualities(
                    node=node.subprogram_parent_node, time_allocations=node.current_program.parent_program.allocations, depth=0)

                return self.find_exact_expected_utility(time_allocations=time_allocations, possible_qualities=self.possible_qualities, expected_utility=1,
                                                        current_qualities=[None for i in range(self.generator_dag.order)], parent_qualities=parent_qualities,
                                                        depth=0, leaves=[node], sum=0)

            # Calculates the EU of a conditional expression
            elif node.expression_type == "conditional" and not node.in_subtree:

                if original_allocations_inner:
                    copied_branch_allocations = [copy.deepcopy(node.true_subprogram.allocations),
                                                 copy.deepcopy(node.false_subprogram.allocations)]

                    node.true_subprogram.allocations = original_allocations_inner[0]

                    node.false_subprogram.allocations = original_allocations_inner[1]

                # Since in conditional, but not in subtree, evaluate the inner probability of the subtree
                probability_and_qualities = self.performance_profile.query_probability_and_quality_from_conditional_expression(
                    node)

                # Multiply the current probability by the performance profile of the conditional node
                probability *= probability_and_qualities[0]

                conditional_quality = probability_and_qualities[1]

                average_qualities.append(conditional_quality)

                if original_allocations_inner:
                    node.true_subprogram.allocations = copied_branch_allocations[0]
                    node.false_subprogram.allocations = copied_branch_allocations[1]

            # Calculates the EU of a for expression
            elif node.expression_type == "for" and not node.in_subtree:

                if original_allocations_inner:

                    copied_branch_allocations = [copy.deepcopy(node.for_subprogram.allocations)]

                    node.for_subprogram.allocations = original_allocations_inner[0]

                    # print("subprogram allocations: {}".format(utils.print_allocations(node.for_subprogram.allocations)))

                # Since in conditional, but not in subtree, evaluate the inner probability of the subtree
                probability_and_qualities = self.performance_profile.query_probability_and_quality_from_for_expression(node)

                # Multiply the current probability by the performance profile of the conditional node
                probability *= probability_and_qualities[0]

                last_for_quality = probability_and_qualities[1]

                average_qualities.append(last_for_quality)

                if original_allocations_inner:
                    node.for_subprogram.allocations = copied_branch_allocations[0]

            else:

                # Get the parents' qualities given their time allocations
                parent_qualities = self.performance_profile.find_parent_qualities(node, time_allocations, depth=0)

                # Outputs a list of qualities from the instances at the specified time given a quality mapping
                qualities = self.performance_profile.query_quality_list_on_interval(time_allocation.time,
                                                                                    time_allocation.node_id,
                                                                                    parent_qualities=parent_qualities)

                # Calculates the average quality on the list of qualities for querying
                average_quality = self.performance_profile.average_quality(qualities)

                average_qualities.append(average_quality)

                probability *= self.performance_profile.query_probability_contract_expression(average_quality,
                                                                                              qualities)

        expected_utility = probability * self.global_utility(average_qualities)

        return expected_utility

    # def find_exact_expected_utility(self, leaves, time_allocations, depth, expected_utility, current_qualities, parent_qualities, possible_qualities, sum) -> float:
    #     """
    #     Returns the parent qualities given the time allocations and node

    #     :param: depth: The depth of the recursive call
    #     :param: node: Node object, finding the parent qualities of this node
    #     :param: time_allocations: float[] (order matters), for the entire DAG
    #     :return: A list of parent qualities
    #     """

    #     # TODO: Make sure that the recursion isnt double counting some branches (9/15)

    #     # Recur down the DAG
    #     depth += 1

    #     if leaves:

    #         for node in leaves:

    #             if node.parents and depth != 1:

    #                 for parent in node.parents:

    #                     # Use the qualities from the previous possible qualities in the parent nodes
    #                     # as parent qualities to query from performance profiles
    #                     parent_qualities.append(current_qualities[parent.id])

    #             # Loop through all possible qualities on the current node
    #             for possible_quality in possible_qualities:

    #                 current_qualities[node.id] = possible_quality

    #                 node_time = time_allocations[node.id].time

    #                 sample_quality_list = self.performance_profile.query_quality_list_on_interval(
    #                     time=node_time, id=node.id, parent_qualities=parent_qualities)

    #                 conditional_probability = self.performance_profile.query_probability_contract_expression(
    #                     queried_quality=possible_quality, quality_list=sample_quality_list)

    #                 # Traverse up the DAG
    #                 new_leaves = node.children

    #                 if depth == self.program_dag.order - 1:
    #                     # Remove nones from the list since current qualities will have model qualities for
    #                     # every node in the generator dag
    #                     utility = self.global_utility(utils.remove_nones_list(current_qualities))

    #                     conditional_probability *= utility
    #                     sum += conditional_probability

    #                 else:

    #                     # The recursion looks funny here, but the += acts as a sum
    #                     expected_utility += conditional_probability * self.find_exact_expected_utility(leaves=new_leaves, time_allocations=time_allocations, depth=depth,
    #                                                                                                    expected_utility=expected_utility, current_qualities=current_qualities,
    #                                                                                                    possible_qualities=possible_qualities, parent_qualities=[], sum=0)

    #         if depth == self.program_dag.order - 1:

    #             return sum

    #         else:

    #             return expected_utility

    #     # If we hit the bottom of the recursion
    #     else:

    #         return sum

    def find_exact_expected_utility(self, leaves, time_allocations, depth, expected_utility, current_qualities, parent_qualities, possible_qualities, sum) -> float:
        """
        Returns the parent qualities given the time allocations and node

        :param: depth: The depth of the recursive call
        :param: node: Node object, finding the parent qualities of this node
        :param: time_allocations: float[] (order matters), for the entire DAG
        :return: A list of parent qualities
        """

        # TODO: Make sure that the recursion isnt double counting some branches (9/15)

        # Recur down the DAG
        depth += 1
        print("DEPTH: {}".format(depth))

        if leaves:

            for node in leaves:
                
                # TODO: Fix THIS error! child of for is the root node !?
                print("LEAVES: {}".format([leaf.id for leaf in leaves]))

                # Check whether the node is a conditional node or a for node
                # If so, skip it since no relevant performance profile can be queried from stored performance profiles
                if node.expression_type == "for" or node.expression_type == "conditional":

                    # Continue on with the recursion with its children
                    leaves.extend(node.children)

                    continue

                if node.parents and depth != 1:

                    for parent in node.parents:

                        # Check parents aren't fors or conditionals
                        if parent.expression_type == "for" or parent.expression_type == "conditional":

                            continue

                        # Use the qualities from the previous possible qualities in the parent nodes
                        # as parent qualities to query from performance profiles
                        parent_qualities.append(current_qualities[parent.id])

                # Loop through all possible qualities on the current node
                for possible_quality in possible_qualities:

                    current_qualities[node.id] = possible_quality

                    node_time = time_allocations[node.id].time

                    print(parent_qualities)
                    print(node.id)
                    sample_quality_list = self.performance_profile.query_quality_list_on_interval(
                        time=node_time, id=node.id, parent_qualities=parent_qualities)

                    conditional_probability = self.performance_profile.query_probability_contract_expression(
                        queried_quality=possible_quality, quality_list=sample_quality_list)

                    # Traverse up the DAG
                    new_leaves = node.children

                    if depth == self.program_dag.order - 1:
                        # Remove nones from the list since current qualities will have model qualities for
                        # every node in the generator dag
                        utility = self.global_utility(utils.remove_nones_list(current_qualities))

                        conditional_probability *= utility
                        sum += conditional_probability

                    else:

                        # The recursion looks funny here, but the += acts as a sum
                        expected_utility += conditional_probability * self.find_exact_expected_utility(leaves=new_leaves, time_allocations=time_allocations, depth=depth,
                                                                                                       expected_utility=expected_utility, current_qualities=current_qualities,
                                                                                                       possible_qualities=possible_qualities, parent_qualities=[], sum=0)

            if depth == self.program_dag.order - 1:

                return sum

            else:

                return expected_utility

        # If we hit the bottom of the recursion (i.e., the root)
        else:

            return sum

    def naive_hill_climbing_no_children_no_parents(self, decay=1.1, threshold=.01, verbose=False) -> List[float]:
        """
        Does outer naive hill climbing search by randomly replacing a set amount of time s between two different contract
        algorithms. If the expected value of the root node of the contract algorithm increases, we commit to the
        replacement; else, we divide s by a decay rate and repeat the above until s reaches some threshold by which we
        terminate.

        :param verbose: Verbose mode
        :param threshold: float, the threshold of the temperature decay during annealing
        :param decay: float, the decay rate of the temperature during annealing
        :return: A stream of optimized time allocations associated with each contract algorithm
        """
        # Initialize the amount of time to be switched
        time_switched = self.initialize_allocations.find_uniform_allocation(self.budget)

        while time_switched > threshold:

            possible_local_max = []

            # Remove the Nones in the list before taking permutations
            refactored_allocations = utils.remove_nones_time_allocations(self.allocations)

            # Go through all permutations of the time allocations
            for permutation in permutations(refactored_allocations, 2):

                # Makes a deep copy to avoid pointers to the same list
                adjusted_allocations = copy.deepcopy(self.allocations)

                # Avoids exchanging time with itself
                if permutation[0].node_id == permutation[1].node_id:
                    continue

                # Avoids negative time allocation
                elif adjusted_allocations[permutation[0].node_id].time - time_switched < 0:
                    continue

                else:
                    adjusted_allocations[permutation[0].node_id].time -= time_switched
                    adjusted_allocations[permutation[1].node_id].time += time_switched

                    if self.global_expected_utility(adjusted_allocations) > self.global_expected_utility(
                            self.allocations):
                        possible_local_max.append(adjusted_allocations)

                    eu_adjusted = self.global_expected_utility(adjusted_allocations) * self.scale
                    eu_original = self.global_expected_utility(self.allocations) * self.scale

                    adjusted_allocations = utils.remove_nones_time_allocations(adjusted_allocations)

                    print_allocations_outer = [i.time for i in adjusted_allocations]

                    temp_time_switched = time_switched

                    # Check for rounding
                    if self.decimals is not None:
                        # utils.print_allocations(adjusted_allocations)
                        print_allocations_outer = [round(i.time, self.decimals) for i in adjusted_allocations]

                        eu_adjusted = round(eu_adjusted, self.decimals)
                        eu_original = round(eu_original, self.decimals)

                        temp_time_switched = round(temp_time_switched, self.decimals)

                    if verbose:
                        message = "Amount of time switched: {:<12} ==> EU(adjusted): {:<12} EU(original): {:<12} ==> Allocations: {}"
                        print(message.format(temp_time_switched, eu_adjusted, eu_original, print_allocations_outer))

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

    def naive_hill_climbing_outer(self, verbose=False) -> List[float]:
        """
        Does outer naive hill climbing search by randomly replacing a set amount of time s between two different contract
        algorithms. If the expected value of the root node of the contract algorithm increases, we commit to the
        replacement; else, we divide s by a decay rate and repeat the above until s reaches some threshold by which we
        terminate.

        :param verbose: Verbose mode
        :param threshold: float, the threshold of the temperature decay during annealing
        :param decay: float, the decay rate of the temperature during annealing
        :return: A stream of optimized time allocations associated with each contract algorithm
        """
        # Check if it has child programs and what type of child programs
        # TODO: Make it more general later to accompany more then one type of child program
        if self.child_programs and self.child_programs[0].subprogram_expression_type == "conditional":

            true_allocations = copy.deepcopy(self.child_programs[0].allocations)
            false_allocations = copy.deepcopy(self.child_programs[1].allocations)

            self.original_allocations_inner = [copy.deepcopy(self.child_programs[0].allocations),
                                               copy.deepcopy(self.child_programs[1].allocations)]

            return self.naive_hill_climbing_outer_conditional(true_allocations, false_allocations, verbose=verbose)

        elif self.child_programs and self.child_programs[0].subprogram_expression_type == "for":

            for_allocations = copy.deepcopy(self.child_programs[0].allocations)

            self.original_allocations_inner = [copy.deepcopy(self.child_programs[0].allocations)]

            return self.naive_hill_climbing_outer_for(for_allocations, verbose=verbose)

        else:

            return self.naive_hill_climbing_no_children_no_parents(verbose=verbose)

    def naive_hill_climbing_outer_conditional(self, true_allocations, false_allocations, decay=1.1, threshold=.01, verbose=False) -> List[float]:
        """

        :param verbose: Verbose mode
        :param threshold: float, the threshold of the temperature decay during annealing
        :param decay: float, the decay rate of the temperature during annealing
        :return: A stream of optimized time allocations associated with each contract algorithm
        """

        # Initialize the amount of time to be switched
        time_switched = self.initialize_allocations.find_uniform_allocation(self.budget)

        while time_switched > threshold:

            possible_local_max = []

            # Remove the Nones in the list before taking permutations
            refactored_allocations = utils.remove_nones_time_allocations(self.allocations)

            # Go through all permutations of the time allocations
            for permutation in permutations(refactored_allocations, 2):

                node_0 = utils.find_node(permutation[0].node_id, self.program_dag)
                node_1 = utils.find_node(permutation[1].node_id, self.program_dag)

                # Makes a deep copy to avoid pointers to the same list
                adjusted_allocations = copy.deepcopy(self.allocations)

                # Avoids exchanging time with itself
                if permutation[0].node_id == permutation[1].node_id:
                    continue

                # Avoids negative time allocation
                elif adjusted_allocations[permutation[0].node_id].time - time_switched < 0:
                    continue

                else:
                    adjusted_allocations[permutation[0].node_id].time -= time_switched
                    adjusted_allocations[permutation[1].node_id].time += time_switched

                    # Does hill climbing on the outer metareasoning problem that is a conditional
                    if node_0.expression_type == "conditional":
                        # Reallocate the budgets for the inner metareasoning problems
                        node_0.true_subprogram.change_budget(copy.deepcopy(adjusted_allocations[node_0.id].time))
                        node_0.false_subprogram.change_budget(copy.deepcopy(adjusted_allocations[node_0.id].time))

                        # Do naive hill climbing on the branches
                        true_allocations = copy.deepcopy(node_0.true_subprogram.naive_hill_climbing_inner(verbose=False))
                        false_allocations = copy.deepcopy(node_0.false_subprogram.naive_hill_climbing_inner())

                    if node_1.expression_type == "conditional":
                        # Reallocate the budgets for the inner metareasoning problems
                        node_1.true_subprogram.change_budget(copy.deepcopy(adjusted_allocations[node_1.id].time))
                        node_1.false_subprogram.change_budget(copy.deepcopy(adjusted_allocations[node_1.id].time))

                        # Do naive hill climbing on the branches
                        true_allocations = copy.deepcopy(node_1.true_subprogram.naive_hill_climbing_inner())
                        false_allocations = copy.deepcopy(node_1.false_subprogram.naive_hill_climbing_inner())

                    # TODO: make a pointer from an element of the list of time allocations to a pointer to the left and right time allocations for conditional time allocations in the outer program
                    if self.global_expected_utility(adjusted_allocations) > self.global_expected_utility(self.allocations, self.original_allocations_inner):

                        possible_local_max.append([adjusted_allocations, true_allocations, false_allocations])

                    eu_adjusted = self.global_expected_utility(adjusted_allocations) * self.scale
                    eu_original = self.global_expected_utility(self.allocations, self.original_allocations_inner) * self.scale

                    adjusted_allocations = utils.remove_nones_time_allocations(adjusted_allocations)

                    print_allocations_outer = [i.time for i in adjusted_allocations]
                    temp_time_switched = time_switched

                    # Check for rounding
                    if self.decimals is not None:
                        print_allocations_outer = [round(i.time, self.decimals) for i in adjusted_allocations]

                        eu_adjusted = round(eu_adjusted, self.decimals)
                        eu_original = round(eu_original, self.decimals)

                        # self.global_expected_utility(self.allocations) * self.scale
                        temp_time_switched = round(temp_time_switched, self.decimals)

                    if verbose:
                        message = "Amount of time switched: {:<12} ==> EU(adjusted): {:<12} EU(original): {:<12} ==> Allocations: {}"
                        print(message.format(temp_time_switched, eu_adjusted, eu_original, print_allocations_outer))

                    # Reset the branches of the inner conditional
                    if self.original_allocations_inner:
                        true_allocations = self.original_allocations_inner[0]
                        false_allocations = self.original_allocations_inner[1]

            # arg max here
            if possible_local_max:

                best_allocation = max(
                    [self.global_expected_utility(j[0]) for j in possible_local_max])

                for j in possible_local_max:

                    if self.global_expected_utility(j[0]) == best_allocation:

                        # Make a deep copy to avoid pointers to the same list
                        self.allocations = copy.deepcopy(j[0])

                        self.original_allocations_inner = [
                            copy.deepcopy(j[1]),
                            copy.deepcopy(j[2])
                        ]

            else:
                time_switched = time_switched / decay

        return [self.allocations, self.original_allocations_inner[0],
                self.original_allocations_inner[1]]

    def naive_hill_climbing_outer_for(self, for_allocations, decay=1.1, threshold=.01, verbose=False) -> List[float]:
        """

        :param verbose: Verbose mode
        :param threshold: float, the threshold of the temperature decay during annealing
        :param decay: float, the decay rate of the temperature during annealing
        :return: A stream of optimized time allocations associated with each contract algorithm
        """

        # Initialize the amount of time to be switched
        time_switched = self.initialize_allocations.find_uniform_allocation(self.budget)

        while time_switched > threshold:
            # print("self.allocations: {}".format([t.time for t in self.allocations]))
            # print("original allocations inner: {}".format([t.time for t in self.original_allocations_inner[0]]))
            possible_local_max = []

            # Remove the Nones in the list before taking permutations
            refactored_allocations = utils.remove_nones_time_allocations(self.allocations)

            # Go through all permutations of the time allocations
            for permutation in permutations(refactored_allocations, 2):

                node_0 = utils.find_node(permutation[0].node_id, self.program_dag)
                node_1 = utils.find_node(permutation[1].node_id, self.program_dag)

                # Makes a deep copy to avoid pointers to the same list
                adjusted_allocations = copy.deepcopy(self.allocations)

                # Avoids exchanging time with itself
                if permutation[0].node_id == permutation[1].node_id:
                    continue

                # Avoids negative time allocation
                elif adjusted_allocations[permutation[0].node_id].time - time_switched < 0:
                    continue

                else:
                    adjusted_allocations[permutation[0].node_id].time -= time_switched
                    adjusted_allocations[permutation[1].node_id].time += time_switched

                    # Does hill climbing on the outer metareasoning problem that is a conditional
                    if node_0.expression_type == "for":

                        # Reallocate the budgets for the inner metareasoning problems
                        node_0.for_subprogram.change_budget(copy.deepcopy(adjusted_allocations[node_0.id].time))

                        # Do naive hill climbing on the branches
                        for_allocations = copy.deepcopy(node_0.for_subprogram.naive_hill_climbing_inner())
                        # print("subprogram allocations: {} end".format(utils.print_allocations(node_0.for_subprogram.allocations)))

                    if node_1.expression_type == "for":

                        # Reallocate the budgets for the inner metareasoning problems
                        node_1.for_subprogram.change_budget(copy.deepcopy(adjusted_allocations[node_1.id].time))

                        # Do naive hill climbing on the branches
                        for_allocations = copy.deepcopy(node_1.for_subprogram.naive_hill_climbing_inner())
                        # print("subprogram allocations: {}".format(utils.print_allocations(node_1.for_subprogram.allocations)))

                    if self.global_expected_utility(adjusted_allocations, [for_allocations]) > self.global_expected_utility(self.allocations, self.original_allocations_inner):

                        possible_local_max.append([adjusted_allocations, for_allocations])
                        # print("for_allocations: {}".format(utils.print_allocations(for_allocations)))

                    # utils.print_allocations(self.original_allocations_inner[0])

                    eu_adjusted = self.global_expected_utility(adjusted_allocations, [for_allocations]) * self.scale
                    eu_original = self.global_expected_utility(self.allocations, self.original_allocations_inner) * self.scale

                    adjusted_allocations = utils.remove_nones_time_allocations(adjusted_allocations)

                    print_allocations_outer = [i.time for i in adjusted_allocations]
                    temp_time_switched = time_switched

                    # Check for rounding
                    if self.decimals is not None:
                        print_allocations_outer = [round(i.time, self.decimals) for i in adjusted_allocations]

                        eu_adjusted = round(eu_adjusted, self.decimals)
                        eu_original = round(eu_original, self.decimals)

                        # self.global_expected_utility(self.allocations) * self.scale
                        temp_time_switched = round(temp_time_switched, self.decimals)

                    if verbose:
                        message = "Amount of time switched: {:<12} ==> EU(adjusted): {:<12} EU(original): {:<12} ==> Allocations: {}"
                        print(message.format(temp_time_switched, eu_adjusted, eu_original, print_allocations_outer))

                    # Reset the branch of the inner for
                    if self.original_allocations_inner:

                        for_allocations = self.original_allocations_inner[0]

            # arg max here
            if possible_local_max:
                # print("possible local max: {}".format([self.global_expected_utility(j[0]) for j in possible_local_max]))

                best_allocation = max([self.global_expected_utility(j[0]) for j in possible_local_max])
                # print("Best Allocation: {}".format(best_allocation))
                for j in possible_local_max:

                    if self.global_expected_utility(j[0]) == best_allocation:

                        # Make a deep copy to avoid pointers to the same list
                        self.allocations = copy.deepcopy(j[0])

                        self.original_allocations_inner = [copy.deepcopy(j[1])]

            else:
                time_switched = time_switched / decay

        return [self.allocations, self.original_allocations_inner[0]]

    def naive_hill_climbing_inner(self, decay=1.1, threshold=.01, verbose=False) -> List[float]:
        """
        Does inner naive hill climbing search on one of the branches of a conditional by randomly replacing a set
        amount of time s between two different contract algorithms. If the expected value of the root node of the
        contract algorithm increases, we commit to the replacement; else, we divide s by a decay rate and repeat the
        above until s reaches some threshold by which we terminate.

        :param verbose: Verbose mode
        :param threshold: float, the threshold of the temperature decay during annealing
        :param decay: float, the decay rate of the temperature during annealing
        :return: A stream of optimized time allocations associated with each contract algorithm
        """
        if self.subprogram_expression_type == "conditional":
            # Check that the net budget doesn't go negative if taxed with tau for inner
            tau = self.performance_profile.calculate_tau()
            taxed_budget = self.budget - tau

        elif self.subprogram_expression_type == "for":
            taxed_budget = self.budget

        # Check if the budget is 0 for the inner metareasoning
        if taxed_budget > 0:

            # Reinitialize the inner metareasoning problem with a uniform budget
            self.allocations = self.initialize_allocations.uniform_budget()

            # Initialize the amount of time to be switched
            time_switched = self.initialize_allocations.find_uniform_allocation(self.budget)

            while time_switched > threshold:

                possible_local_max = []

                # Remove the Nones in the list before taking permutations
                refactored_allocations = utils.remove_nones_time_allocations(self.allocations)

                # Go through all permutations of the time allocations
                for permutation in permutations(refactored_allocations, 2):

                    node_0 = utils.find_node(permutation[0].node_id, self.program_dag)
                    node_1 = utils.find_node(permutation[1].node_id, self.program_dag)

                    # Makes a deep copy to avoid pointers to the same list
                    adjusted_allocations = copy.deepcopy(self.allocations)

                    # Avoids exchanging time with itself
                    if permutation[0].node_id == permutation[1].node_id:
                        continue

                    # Avoids all permutations that include the conditional node in the inner metareasoning problem
                    elif node_0.expression_type == "conditional" or node_1.expression_type == "conditional":
                        continue

                    # Avoids all permutations that include the for node in the inner metareasoning problem
                    elif node_0.expression_type == "for" or node_1.expression_type == "for":
                        continue

                    # Avoids negative time allocation
                    elif adjusted_allocations[permutation[0].node_id].time - time_switched < 0:
                        continue

                    else:
                        adjusted_allocations[permutation[0].node_id].time -= time_switched
                        adjusted_allocations[permutation[1].node_id].time += time_switched

                        # utils.print_allocations(adjusted_allocations)
                        # utils.print_allocations(self.allocations)

                        # TODO: make a pointer from an element of the list of time allocations to a pointer to the left and right time allocations for conditional time allocations in the outer program
                        if self.global_expected_utility(adjusted_allocations) > self.global_expected_utility(self.allocations):
                            possible_local_max.append(adjusted_allocations)

                        eu_adjusted = self.global_expected_utility(adjusted_allocations) * self.scale
                        eu_original = self.global_expected_utility(self.allocations) * self.scale

                        adjusted_allocations = utils.remove_nones_time_allocations(adjusted_allocations)

                        print_allocations_outer = [i.time for i in adjusted_allocations]

                        temp_time_switched = time_switched

                        # Check for rounding
                        if self.decimals is not None:

                            print_allocations_outer = [round(i.time, self.decimals) for i in adjusted_allocations]

                            eu_adjusted = round(eu_adjusted, self.decimals)
                            eu_original = round(eu_original, self.decimals)

                            # self.global_expected_utility(self.allocations) * self.scale
                            temp_time_switched = round(temp_time_switched, self.decimals)

                        if verbose:

                            message = "Amount of time switched: {:<12} ==> EU(adjusted): {:<12} EU(original): {:<12} ==> Allocations: {}"
                            print(message.format(temp_time_switched, eu_adjusted, eu_original,
                                                 print_allocations_outer))

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

            utils.print_allocations(self.allocations)

            return self.allocations

        else:

            for time_allocation in self.allocations:
                if time_allocation.time is not None and not Node.is_conditional_node(
                        utils.find_node(time_allocation.node_id, self.program_dag)):
                    time_allocation.time = 0

            return self.allocations

    def change_budget(self, new_budget) -> None:
        """
        Changes the budget of the contract program and adjusts the objects that use the budget of the
        contract program

        :param new_budget: float
        :return: None
        """
        self.budget = new_budget
        self.initialize_allocations.budget = new_budget

    @staticmethod
    def find_leaves(dag):
        leaves = []
        root = dag.root

        for parent in root.parents:
            if parent.parents == [] or parent.parents is None:
                leaves.append(parent)

        return leaves
