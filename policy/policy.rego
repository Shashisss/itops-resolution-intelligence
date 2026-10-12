# Policy-governed autonomy (reference OPA policy).
# Risk class decides whether an action may run autonomously or needs a human.
package itops

default allow = false

# read / recommend: always allowed
allow { input.mode == "Autonomous" }

# low-risk automated actions: allowed
allow { input.mode == "Auto" }

# policy-controlled or production actions: only with approval
allow { input.mode == "Policy controlled"; input.approved == true }
allow { input.mode == "Human approval"; input.approved == true }
