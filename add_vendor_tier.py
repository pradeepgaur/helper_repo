how can i create this in excel negative_or_null_est_ind

4:10 PM
negative_or_null_est_ind flags estimates where the total amount is zero, negative, or missing. In Excel it's a simple formula checking est_tot_amt.

Assuming est_tot_amt is in column G, in a new column put:

excel
=IF(OR(G2<0, G2=0, G2="", ISBLANK(G2)), 1, 0)
