create table IF NOT EXISTS `league` (
  `ID` int(11) NOT NULL auto_increment,
  `User` bigint NOT NULL,
  `Appearance` int(11) default 0,
  `Score` int(11) default 0,
  `Win` int(11) default 0,
  `Tie` int(11) default 0,
  `Lose` int(11) default 0,
  `Goal` int(11) default 0,
  `Lost_Goal` int(11) default 0,
  primary key(`id`)
) default charset = utf8;