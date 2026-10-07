# Open Dicke PIQS software convention (frozen)

Source: QuTiP PIQS, "Superradiance: Open Dicke Model."

Use the tutorial parameterization as ONE coherent convention. Do not mix
coefficients from a ladder-operator Hamiltonian with the `Jx` operator.

## Coupling / interaction
- `g = 2/sqrt(N)`.
- `h_int = g * tensor(a + a.dag(), jx)` where `jx = jspin(N)[0]`.
- `J+ + J- = 2*Jx` is a true identity, but when you translate a
  ladder-operator Hamiltonian `g*(a^dag+a)*(J+ + J-)` into a `Jx` Hamiltonian
  the coefficient translates too. The tutorial coefficient `g` already pairs
  with `Jx`; adding a SECOND factor of 2 doubles the physical coupling and
  changes the model. Keep `g = 2/sqrt(N)` with `Jx` and add the interaction
  commutator only once.

## Photon cutoff
- `n_max` is passed directly as the dimension of `destroy`: `a = destroy(n_max)`
  (16 -> a 16-dimensional Fock space).

## Liouvillian assembly
1. Spin: build with PIQS `Dicke` rate interface; set `ensemble.hamiltonian =
   w0*Jz` ONCE; set only the rates present in the case; `L_spin =
   ensemble.liouvillian()`.
2. Cavity: `h_c = wc*a.dag()*a`; cavity loss collapse operator `sqrt(kappa)*a`;
   `L_cav = liouvillian(h_c, [sqrt(kappa)*a])`.
3. Promote identities to superoperators via `to_super(identity(...))`.
4. Combine: `L = super_tensor(L_cav, id_spin) + super_tensor(id_cav, L_spin)`.
   Cavity is subsystem 0.
5. Add interaction once: `L -= 1j*(spre(h_int) - spost(h_int))`.

## Steady state and reduction
- `rho_ss = steadystate(L)` has dims `[[n_max, nds], [n_max, nds]]`.
- `rho_cav = rho_ss.ptrace(0)` because the cavity is subsystem 0.

## PIQS rate names (map from the physics symbols)
- `dephasing`           = local dephasing  gamma_phi
- `pumping`             = local pumping    gamma_up (up-arrow)
- `emission`            = local emission   gamma_down (down-arrow)
- `collective_pumping`  = collective pumping   gamma_Up (double up-arrow)
- `collective_emission` = collective emission  gamma_Down (double down-arrow)
- `collective_dephasing`= collective dephasing
`kappa` is the cavity loss and is applied in every case.

## Validation (no reference values)
- Small instance first: dims, subsystem order (index 0 == cavity), trace ~ 1,
  Hermiticity ~ 0, steady residual `||L*vec(rho_ss)|| ~ 0`, Wigner norm ~ 1.
- Each full grid: shape, finiteness, axis ordering, normalization
  `sum(W)*dx*dp ~ 1`, and distinctness across the cases.
