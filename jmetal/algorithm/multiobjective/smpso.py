from copy import copy
from random import Random
from typing import TypeVar, List

import numpy

from jmetal.component.archive import BoundedArchive
from jmetal.component.evaluator import Evaluator, SequentialEvaluator
from jmetal.core.algorithm import ParticleSwarmOptimization
from jmetal.core.operator import Mutation
from jmetal.core.problem import FloatProblem
from jmetal.core.solution import FloatSolution
from jmetal.util.comparator import DominanceComparator
from jmetal.util.observable import Observable, DefaultObservable

R = TypeVar('R')


class SMPSO(ParticleSwarmOptimization):
    def __init__(self,
                 problem: FloatProblem,
                 swarm_size: int,
                 max_evaluations: int,
                 mutation: Mutation[FloatSolution],
                 leaders: BoundedArchive[FloatSolution],
                 observable: Observable = DefaultObservable(),
                 evaluator: Evaluator[FloatSolution] = SequentialEvaluator[FloatSolution]()):
        super(SMPSO, self).__init__()
        self.problem = problem
        self.swarm_size = swarm_size
        self.max_evaluations = max_evaluations
        self.mutation : Mutation[FloatSolution] = mutation
        self.leaders = leaders
        self.observable = observable
        self.evaluator = evaluator

        self.evaluations = 0

        self.c1_min = 1.5
        self.c1_max = 2.5
        self.c2_min = 1.5
        self.c2_max = 2.5

        self.min_weight = 0.1
        self.max_weight = 0.1

        self.change_velocity1 = -1
        self.change_velocity2 = -1

        self.dominance_comparator = DominanceComparator()

        self.speed = numpy.zeros((self.swarm_size, self.problem.number_of_variables), dtype=float)
        self.delta_max = numpy.empty(problem.number_of_variables)
        self.delta_min = numpy.empty(problem.number_of_variables)
        for i in range(problem.number_of_variables):
            self.delta_max[i] = (self.problem.upper_bound[i] - self.problem.lower_bound[i]) / 2.0

        self.delta_min = -1.0 * self.delta_max

    def init_progress(self) -> None :
        self.evaluations = self.swarm_size
        self.leaders.compute_density_estimator()

    def update_progress(self) -> None :
        self.evaluations += self.swarm_size
        self.leaders.compute_density_estimator()

        observable_data = {'evaluations': self.evaluations,
                           'population': self.swarm,
                           'computing time': self.get_current_computing_time()}
        self.observable.notify_all(**observable_data)

    def is_stopping_condition_reached(self) -> bool:
        return self.evaluations >= self.max_evaluations

    def create_initial_swarm(self) -> List[FloatSolution]:
        swarm = []

        for i in range(self.swarm_size):
            swarm.append(self.problem.create_solution())

        return swarm

    def evaluate_swarm(self, swarm: List[FloatSolution]) -> List[FloatSolution]:
        return self.evaluator.evaluate(swarm, self.problem)

    def initialize_global_best(self, swarm: List[FloatSolution]) -> None:
        for particle in self.swarm:
            self.leaders.add(particle)

    def initialize_particle_best(self, swarm: List[FloatSolution]) -> None:
        for particle in self.swarm:
            particle.attributes["local_best"] = copy(particle)

    def initialize_velocity(self, swarm: List[FloatSolution]) -> None:
        pass # Velocity initialized in the constructor

    def update_velocity(self, swarm: List[FloatSolution]) -> None:
        for i in range(self.swarm_size):
            particle = copy(self.swarm[i])
            best_particle = copy(self.swarm[i].attributes["local_best"])
            best_global = self.__select_global_best()

            r1 = Random.random()
            r2 = Random.random()

            c1 = Random.uniform(self.c1_min, self.c1_max)
            c2 = Random.uniform(self.c2_min, self.c2_max)

            wmin = self.min_weight
            wmax = self.max_weight

            for var in range(self.problem.number_of_variables):
                self.speed[i][var] = \
                    self.__velocity_constriction(self.__constriction_coefficient(c1, c2) * \
                                                 (wmax * self.speed[i][var] +
                                                  c1 * r1 * (best_particle.variables[var] - particle.variables[var]) +
                                                  c2 * r2 * (best_global.variables[var] - particle.variables[var])),
                                                 var)

    def update_position(self, swarm: List[FloatSolution]) -> None:
        for i in range(self.swarm_size):
            particle = self.swarm[i]

            for j in particle.variables:
                particle.variables[j] += self.speed[i][j]

                if particle.variables[j] < self.problem.lower_bound[j]:
                    particle.variables[j] = self.problem.lower_bound[j]
                    self.speed[i][j] *= self.change_velocity1

                if particle.variables[j] > self.problem.upper_bound[j]:
                    particle.variables[j] = self.problem.upper_bound[j]
                    self.speed[i][j] *= self.change_velocity2

    def perturbation(self, swarm: List[FloatSolution]) -> None:
        for particle in self.swarm:
            self.mutation.execute(particle)

    def update_global_best(self, swarm: List[FloatSolution]) -> None:
        for particle in self.swarm:
            self.leaders.add(copy(particle))

    def update_particle_best(self, swarm: List[FloatSolution]) -> None:
        for i in range(self.swarm_size):
            flag = self.dominance_comparator.compare(
                self.swarm[i],
                self.swarm[i].attribute["local_best"])

            if flag is not 1:
                swarm[i].attributes["local_best"] = copy(self.swarm[i])

    def get_result(self) -> List[FloatSolution]:
        self.leaders.solution_list

    def __select_global_best(self) -> FloatSolution:
        #pos1 = Random.randint(0, len(self.leaders.solution_list) - 1)
        #pos2 = Random.randint(0, len(self.leaders.solution_list) - 1)
        best_global = None
        particles = Random.sample(self.leaders.solution_list, 2)
        if self.leaders.get_comparator().compare(particles[0], particles[1]) < 1:
            best_global = copy(particles[0])
        else:
            best_global = copy(particles[1])

        return best_global

    def __velocity_constriction(self, value: float, variable_index: int) -> float:
        result = None
        if value > self.delta_max[variable_index]:
            result = self.delta_max[variable_index]

        if value < self.delta_min[variable_index]:
            result = self.delta_min[variable_index]

        return result

    def __constriction_coefficient(self, c1: float, c2: float) -> float:
        result = 0.0
        rho = c1 + c2
        if rho <= 4:
            result = 1.0
        else:
            result = 2.0 / (2.0 - rho - numpy.sqrt(pow(rho, 2.0) - 4.0 * rho))

        return result
